"""Same thesis gates under independent local rules and metre-based CRSs."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from stage1.catalogue import KOELN_POLICY, SOURCES
from stage1.configuration import planning_config, resolve_config, structure_errors
from stage1.engine import aggregate, evaluate_design, evaluate_muriel, groundwater
from stage1.profiles import profile_template, source_registry, validate_policy


def local_profile(jurisdiction='Example authority', reference='Synthetic local criteria'):
    p=profile_template();p.update(profile_kind='custom',profile_id='synthetic_local_v1',municipality=jurisdiction,rule_scope=jurisdiction,
        profile_reviewed=True,profile_review_ref='SYNTHETIC_TEST_REVIEW',groundwater_floor_m=1.2,groundwater_preferred_m=2.,
        neighbour_setback_m=4.,basement_recommended_m=8.,asset_clearance_m=2.,
        protection_zones={'excluded':['RED'],'outer':['AMBER'],'outside':['CLEAR'],'shaft_excluded':['RED','AMBER']},
        sewer_strip_bands=[{'min_diameter_cm':0.,'total_width_m':12.}],
        references={'LOCAL_TEST':{'citation':reference,'locator':'Software fixture, not actual law','url':'','status':'synthetic'}},
        rule_sources={role:'LOCAL_TEST' for role in ('infiltration','groundwater','assets','roof')})
    return p


class TransferRulesTests(unittest.TestCase):
    def test_new_project_has_no_kalk_event_return_period_units_crs_or_rules(self):
        c=planning_config()
        self.assertEqual(c['policy']['profile_kind'],'generic')
        self.assertEqual(c['scenario_id'],'REQUIRED');self.assertIsNone(c['stated_return_period_years'])
        self.assertEqual(c['crs'],'');self.assertIsNone(c['flood']['units'])
        self.assertIsNone(c['policy']['neighbour_setback_m']);self.assertIsNone(c['policy']['protection_zones'])
        self.assertFalse(c['muriel']['enabled'])

    def test_generic_allows_new_jurisdiction_without_importing_local_thresholds(self):
        p=validate_policy({'municipality':'A different country / region'})
        rows=groundwater({'protection_zone':'II','neighbour_distance_m':1.,'evidence_ref':'TEST'},p)
        self.assertEqual(aggregate(rows),'CONDITIONAL')
        self.assertTrue(all(d.source_id=='THESIS' for d in rows))
        self.assertEqual(next(d.status for d in rows if d.rule_id=='protection_zone'),'CONDITIONAL')

    def test_known_site_failure_stays_fail_without_a_local_numeric_profile(self):
        for evidence in ({'receiving_ground_clean':False},{'infiltration_prohibited':True}):
            self.assertEqual(aggregate(groundwater(evidence,{})),'FAIL')

    def test_koeln_cannot_be_moved_by_a_review_checkbox(self):
        for reviewed in (False,True):
            with self.assertRaisesRegex(ValueError,'Köln profile'):
                validate_policy({**KOELN_POLICY,'municipality':'Other authority','profile_reviewed':reviewed,'profile_review_ref':'TEST'})

    def test_legacy_named_koeln_profile_remains_explicit(self):
        p=validate_policy({'profile_id':'koeln_thesis_provisional_v1'})
        self.assertEqual(p['neighbour_setback_m'],2.)
        self.assertEqual(p['protection_zones']['excluded'],['I','II'])

    def test_custom_thresholds_and_zone_codes_drive_the_actual_rules(self):
        from tests.test_engine import gw_evidence,DESIGN
        a=gw_evidence(1.);a.update(protection_zone='CLEAR',neighbour_distance_m=4.)
        rows=groundwater(a,local_profile(),DESIGN,'DHHN2016','HIGH')
        self.assertEqual(next(d.status for d in rows if d.rule_id=='groundwater_clearance'),'FAIL')
        a['module_base_elevation_m__'+DESIGN]=2.5
        self.assertEqual(aggregate(groundwater(a,local_profile(),DESIGN,'DHHN2016','HIGH')),'ADMISSIBLE')
        a['protection_zone']='RED'
        self.assertEqual(aggregate(groundwater(a,local_profile(),DESIGN,'DHHN2016','HIGH')),'FAIL')

    def test_custom_asset_band_and_citation_replace_city_constants(self):
        import ast
        rows=evaluate_design({'land_type':'open_space','public_drainage_assets_present':True,'sewer_profile_cm':50,
                             'sewer_centerline_distance_m':4.,'asset_edge_distance_m':3.},'rain_garden_lined',local_profile())
        rule=next(r for r in rows if r.rule_id=='sewer_protection_strip')
        self.assertEqual(rule.status,'CONDITIONAL')
        self.assertEqual(ast.literal_eval(rule.observed)['strip_total_width_m'],12.)
        self.assertEqual(rule.record()['citation'],'Synthetic local criteria')
        self.assertEqual(rule.source_id,'LOCAL_TEST')

    def test_local_rule_severity_and_exception_route_are_not_universal(self):
        from tests.test_engine import gw_evidence,DESIGN
        a=gw_evidence(1.5);a.update(protection_zone='CLEAR',neighbour_distance_m=4.,non_waterproof_basement_present=True,basement_distance_m=7.)
        p=local_profile();p['groundwater_intermediate_action']='FAIL'
        rows=groundwater(a,p,DESIGN,'DHHN2016','HIGH')
        self.assertEqual(next(d.status for d in rows if d.rule_id=='groundwater_clearance'),'FAIL')
        self.assertEqual(next(d.status for d in rows if d.rule_id=='basement_distance_m'),'CONDITIONAL')
        p.update(basement_setback_recommended=False,groundwater_intermediate_action='EXCEPTION',groundwater_exception_fields=['local_exception_signed'])
        a['local_exception_signed']=True
        rows=groundwater(a,p,DESIGN,'DHHN2016','HIGH')
        self.assertEqual(next(d.status for d in rows if d.rule_id=='basement_distance_m'),'FAIL')
        self.assertEqual(next(d.status for d in rows if d.rule_id=='groundwater_clearance'),'ADMISSIBLE')

    def test_surveyed_corridor_can_replace_diameter_band_and_incompatibility_fails(self):
        p=local_profile();p['sewer_strip_bands']=[]
        a={'land_type':'open_space','public_drainage_assets_present':True,'asset_edge_distance_m':3.,'sewer_corridor_compatible':True}
        rows=evaluate_design(a,'rain_garden_lined',p)
        self.assertEqual(next(d.status for d in rows if d.rule_id=='sewer_protection_strip'),'ADMISSIBLE')
        a['sewer_corridor_compatible']=False
        self.assertEqual(next(d.status for d in evaluate_design(a,'rain_garden_lined',p) if d.rule_id=='sewer_protection_strip'),'FAIL')

    def test_unreferenced_numeric_rules_do_not_become_governing_thresholds(self):
        p=local_profile();p.update(profile_reviewed=False,references={},rule_sources={})
        rows=groundwater({'protection_zone':'RED','neighbour_distance_m':0.},p)
        self.assertEqual(aggregate(rows),'CONDITIONAL')
        self.assertIn('local_rule_sources',[r.rule_id for r in rows])
        p['profile_reviewed']=True
        with self.assertRaisesRegex(ValueError,'cited sources'):validate_policy(p)

    def test_reference_binding_does_not_leak_between_runs_or_change_global_sources(self):
        before=deepcopy(SOURCES)
        first=groundwater({'protection_zone':'RED'},local_profile(reference='First jurisdiction source'))
        second=groundwater({'protection_zone':'RED'},local_profile(reference='Second jurisdiction source'))
        self.assertEqual(next(d.record()['citation'] for d in first if d.rule_id=='protection_zone'),'First jurisdiction source')
        self.assertEqual(next(d.record()['citation'] for d in second if d.rule_id=='protection_zone'),'Second jurisdiction source')
        self.assertEqual(SOURCES,before)

    def test_generic_registry_does_not_list_unselected_municipal_rules(self):
        c=planning_config();c['policy']=validate_policy(c['policy'])
        self.assertEqual(set(source_registry(c)),{'THESIS','USER_DEPTH'})

    def test_profile_scope_and_invalid_return_period_are_checked(self):
        c=planning_config(crs='EPSG:32631',scenario='TEST_EVENT',jurisdiction='Other authority')
        c['policy']=local_profile();c['stated_return_period_years']=-1
        self.assertTrue(any('jurisdiction' in e for e in structure_errors(c)))
        self.assertTrue(any('return_period' in e for e in structure_errors(c)))

    def test_muriel_reference_needs_local_adoption_and_scope(self):
        from tests.test_muriel import metrics
        m=metrics(overlap_fraction=.8,criteria_applicability_required=True)
        self.assertEqual(evaluate_muriel(m)[0],'EVIDENCE_GAP')
        m.update(criteria_adoption_ref='SYNTHETIC_LOCAL_ADOPTION',criteria_scope_matches=True,criteria_source=deepcopy(SOURCES['MURIEL']))
        result,rows=evaluate_muriel(m)
        self.assertEqual(result,'PROTECT_RETENTION')
        self.assertEqual(next(d.source_id for d in rows if d.rule_id=='MURIEL_AREA'),'MURIEL_CRITERIA')

    def test_malformed_or_conflicting_profile_values_are_rejected(self):
        for change in ({'neighbour_setback_m':True},{'groundwater_floor_m':None},
                       {'sewer_strip_bands':[{'min_diameter_cm':10.,'total_width_m':4.}]},
                       {'rule_sources':{'infiltration':'KOELN2022'}},
                       {'protection_zones':{'excluded':['X'],'outer':[],'outside':['X'],'shaft_excluded':[]}}):
            with self.subTest(change=change),self.assertRaises(ValueError):validate_policy({**local_profile(),**change})


@unittest.skipUnless(importlib.util.find_spec('qgis'),'Use QGIS Python')
class TransferGISTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from qgis.core import QgsApplication
        cls.app=QgsApplication.instance() or QgsApplication([],False);cls.app.initQgis()

    def test_end_to_end_two_regions_different_crss_depth_units_and_no_city_rules(self):
        from stage1.demo import create_area_demo
        from stage1.gis import run
        from qgis.core import QgsProject
        summaries=[]
        with tempfile.TemporaryDirectory(prefix='nbs-transfer-') as tmp:
            for i,(crs,units) in enumerate([('EPSG:32631','cm'),('EPSG:32734','m')]):
                source=create_area_demo(Path(tmp)/str(i),crs=crs,depth_units=units)
                if i==1:
                    c=json.loads(source.read_text());c['preparation']={'enabled':True};source.write_text(json.dumps(c))
                out=run(source,False)
                summaries.append(json.loads((out/'planning_summary.json').read_text())['flood_need_area_m2'])
                project=QgsProject();self.assertTrue(project.read(str(out/'stage1.qgz')))
                self.assertEqual(project.crs().authid(),crs);self.assertTrue(all(l.isValid() for l in project.mapLayers().values()))
                with sqlite3.connect(out/'stage1.gpkg') as db:
                    ids={r[0] for r in db.execute('SELECT source_id FROM source_registry')}
                    self.assertFalse(ids & {'KOELN2022','ROOF2026','STEB2025','DWA_SUMMARY'})
                    self.assertEqual(db.execute("SELECT count(*) FROM planning_opportunities WHERE status='ADMISSIBLE'").fetchone()[0],0)
                report=(out/'report.html').read_text();self.assertNotIn('StEB',report)
                snapshot=json.loads((out/'rule_profile.json').read_text());self.assertIsNone(snapshot['stated_return_period_years'])
                self.assertEqual(snapshot['profile']['profile_kind'],'generic');project.clear()
        self.assertEqual(summaries[0],summaries[1])

    def test_full_custom_run_exports_its_own_sources_and_profile_snapshot(self):
        from stage1.demo import create_area_demo
        from stage1.gis import memory_layer,write_layer,run
        from qgis.core import QgsCoordinateReferenceSystem,QgsGeometry,QgsRectangle
        with tempfile.TemporaryDirectory(prefix='nbs-local-rules-') as tmp:
            source=create_area_demo(Path(tmp)/'demo');c=json.loads(source.read_text())
            c['policy']=local_profile(c['jurisdiction'],'Synthetic non-Köln authority document')
            path=source.parent/'inputs/local_evidence.gpkg'
            geom=QgsGeometry.fromRect(QgsRectangle(360000,5639940,360040,5640000))
            write_layer(path,memory_layer('evidence',[({'zone':'RED','ref':'SYNTHETIC_ZONE_SURVEY'},geom)],QgsCoordinateReferenceSystem(c['crs'])),'evidence',first=True)
            c['evidence']=[{'path':str(path),'layer':'evidence','join':'spatial','fields':{'protection_zone':'zone','evidence_ref':'ref'}}]
            source.write_text(json.dumps(c));out=run(source,False)
            with sqlite3.connect(out/'stage1.gpkg') as db:
                self.assertGreater(db.execute("SELECT count(*) FROM groundwater_screen WHERE status='FAIL'").fetchone()[0],0)
                self.assertEqual(db.execute("SELECT DISTINCT citation FROM decision_audit WHERE rule_id='protection_zone' AND status='FAIL'").fetchall(),[('Synthetic non-Köln authority document',)])
                self.assertEqual(db.execute("SELECT count(*) FROM source_registry WHERE source_id='KOELN2022'").fetchone()[0],0)
            snapshot=json.loads((out/'rule_profile.json').read_text())
            self.assertEqual(snapshot['profile']['protection_zones']['excluded'],['RED'])
            self.assertEqual(snapshot['jurisdiction'],c['jurisdiction'])

    def test_run_with_unadopted_muriel_and_adapted_locally_cited_criteria(self):
        from stage1.demo import create_muriel_demo
        from stage1.gis import run
        with tempfile.TemporaryDirectory(prefix='nbs-local-muriel-') as tmp:
            source=create_muriel_demo(Path(tmp)/'demo');c=json.loads(source.read_text())
            c.update(jurisdiction='Different authority',policy=local_profile('Different authority'),designs=['lined_detention'],output_dir='unadopted')
            c['muriel'].update(criteria_scope='Different authority',criteria_adoption_ref=None)
            source.write_text(json.dumps(c));out=run(source,False)
            with sqlite3.connect(out/'stage1.gpkg') as db:
                self.assertEqual(db.execute("SELECT DISTINCT planning_class FROM muriel_priority").fetchall(),[('EVIDENCE_GAP',)])
            c['output_dir']='adopted';c['muriel'].update(criteria_adoption_ref='SYNTHETIC_LOCAL_METHOD_REGISTRATION',criteria_profile_id='synthetic_method_v1',
                criteria_source={'citation':'Synthetic adapted public-space screen','locator':'Test configuration, not a real authority method','url':'','status':'synthetic'})
            c['muriel']['thresholds']['min_area_m2']=2500
            source.write_text(json.dumps(c));out=run(source,False)
            with sqlite3.connect(out/'stage1.gpkg') as db:
                self.assertEqual(db.execute("SELECT DISTINCT citation FROM decision_audit WHERE rule_id='MURIEL_AREA'").fetchall(),[('Synthetic adapted public-space screen',)])
                self.assertGreater(db.execute("SELECT count(*) FROM muriel_priority WHERE planning_class='PROTECT_RETENTION'").fetchone()[0],0)

    def test_preparation_search_extension_covers_largest_local_muriel_radius(self):
        from stage1.demo import create_muriel_demo
        from stage1.preparation import prepare_run
        with tempfile.TemporaryDirectory(prefix='nbs-local-radius-') as tmp:
            source=create_muriel_demo(Path(tmp)/'demo');c=json.loads(source.read_text())
            c['preparation']={'enabled':True};c['muriel']['thresholds']['municipal_distance_m']=450
            source.write_text(json.dumps(c));prepared=prepare_run(source)
            manifest=json.loads((prepared.parent/'preparation_manifest.json').read_text())
            self.assertEqual(manifest['search_buffer_m'],450.)

    def test_cli_initializer_records_only_explicit_location_and_scenario_settings(self):
        import subprocess
        with tempfile.TemporaryDirectory(prefix='nbs-init-transfer-') as tmp:
            target=Path(tmp)/'run.json'
            result=subprocess.run(['/usr/bin/python3','-m','stage1','init',str(target),'--area','Test area','--scenario','TEST_EVENT',
                                   '--crs','EPSG:32734','--jurisdiction','Test authority','--depth-units','m'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            c=json.loads(target.read_text());self.assertEqual(c['crs'],'EPSG:32734');self.assertEqual(c['scenario_id'],'TEST_EVENT')
            self.assertIsNone(c['stated_return_period_years']);self.assertIsNone(c['policy']['neighbour_setback_m'])

    def test_custom_restrictive_zone_is_retained_even_on_a_small_overlay(self):
        from stage1.gis import indexed,join_evidence
        from qgis.core import QgsGeometry,QgsRectangle
        box=lambda x,w:QgsGeometry.fromRect(QgsRectangle(x,0,x+w,10))
        idx,records=indexed([(box(0,.1),{'code':'RED'}),(box(.1,9.9),{'code':'CLEAR'})])
        result=join_evidence(box(0,10),idx,records,{'protection_zone':'code'},zone_priority=['RED','AMBER'])
        self.assertEqual(result['protection_zone'],'RED')
        self.assertEqual(aggregate(groundwater(result,local_profile())),'FAIL')

    def test_new_panel_is_neutral_and_uses_a_declared_non_nrw_crs(self):
        from stage1.planning_gui import PlanningDialog
        from stage1.demo import create_area_demo
        from qgis.core import QgsProject,QgsRasterLayer,QgsVectorLayer
        with tempfile.TemporaryDirectory(prefix='nbs-transfer-ui-') as tmp:
            source=create_area_demo(Path(tmp)/'data',crs='EPSG:32734');config=resolve_config(source)
            dialog=PlanningDialog();self.assertEqual(dialog.area.text(),'');self.assertEqual(dialog.scenario.text(),'')
            self.assertEqual(dialog.period.value(),0);self.assertFalse(dialog.processing_crs.crs().isValid())
            dialog.area.setText('Southern synthetic study');dialog.scenario.setText('LOCAL_EVENT')
            dialog.jurisdiction.setText('Synthetic southern authority');dialog.units.setCurrentIndex(dialog.units.findData('cm'));dialog.folder.setText(tmp)
            raster=QgsRasterLayer(config['flood']['path'],'synthetic flood')
            boundary=QgsVectorLayer(config['study_area']['path']+'|layername=study_area','synthetic boundary','ogr')
            for layer in (raster,boundary):QgsProject.instance().addMapLayer(layer)
            dialog.flood.combo.setLayer(raster);dialog.boundary.combo.setLayer(boundary)
            output=dialog.configuration();self.assertEqual(output['crs'],'EPSG:32734')
            self.assertTrue(dialog.check_inputs()[1].ok)
            self.assertIsNone(output['policy']['groundwater_floor_m']);dialog.close()
            for layer in (raster,boundary):QgsProject.instance().removeMapLayer(layer.id())
