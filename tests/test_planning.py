"""Decision boundaries and complete small-input planning / advanced coexistence."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from stage1.configuration import planning_config, resolve_config, structure_errors
from stage1.planning import FAMILIES, delivery_action, opportunity


class PlanningRulesTests(unittest.TestCase):
    def test_no_planning_match_claims_final_admissibility(self):
        for land in ('roof','open_space','verge','pavement','parking','footway',None,'UNMAPPED'):
            for family in FAMILIES:
                result = opportunity({'land_type':land,'flood_depth_m':.2}, family, 'ADMISSIBLE', .1)
                self.assertIn(result['status'], ('CONDITIONAL','NOT_APPLICABLE'))
                self.assertNotEqual(result['infiltration_status'], 'ADMISSIBLE')

    def test_known_infiltration_fail_is_preserved_in_lined_concept(self):
        result = opportunity({'land_type':'open_space','flood_depth_m':.2}, 'rain_garden', 'FAIL', .1)
        self.assertEqual(result['status'],'CONDITIONAL')
        self.assertEqual(result['infiltration_status'],'FAIL')
        self.assertIn('separate lined',result['pathway'])

    def test_roof_does_not_inherit_ground_infiltration_gate(self):
        result = opportunity({'land_type':'roof'},'roof_control','FAIL',.1)
        self.assertEqual(result['infiltration_status'],'NOT_APPLICABLE')
        self.assertEqual(result['opportunity_class'],'INVESTIGATE')

    def test_below_threshold_sources_remain_and_unknown_depth_is_explicit(self):
        source = opportunity({'land_type':'roof','flood_depth_m':0},'roof_control','CONDITIONAL',.1)
        self.assertEqual(source['need_local'],'NO')
        self.assertEqual(source['opportunity_class'],'INVESTIGATE')
        self.assertIn('connection unverified',source['explanation'])
        unknown = opportunity({'land_type':'roof','flood_depth_m':None},'roof_control','CONDITIONAL',.1)
        self.assertEqual(unknown['need_local'],'UNKNOWN')

    def test_invalid_mapping_and_physical_combinations_rejected(self):
        config = planning_config(flood={'path':'f.tif','type':'raster','units':'cm'},study_area={'path':'a.gpkg'})
        config['planning']['surfaces'] = {'path':'s.gpkg','class_field':'land','mapping':{'a':'invented'}}
        config['combinations'] = [{'id':'physical'}]
        errors = structure_errors(config)
        self.assertTrue(any('category' in e for e in errors))
        self.assertTrue(any('physical combinations' in e for e in errors))
        config['planning']['surfaces']['mapping'] = {'a':['not a category']}
        self.assertTrue(any('category' in e for e in structure_errors(config)))

    def test_private_ownership_has_a_delivery_route(self):
        self.assertIn('landowner', delivery_action('private'))
        self.assertIn('cadastral', delivery_action('unknown'))


@unittest.skipUnless(importlib.util.find_spec('qgis'), 'Use QGIS Python')
class PlanningGISTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from qgis.core import QgsApplication
        cls.app = QgsApplication.instance() or QgsApplication([],False); cls.app.initQgis()
        cls.tmp = tempfile.TemporaryDirectory(prefix='nbs-planning-'); cls.root = Path(cls.tmp.name)
        from stage1.demo import create_planning_demo
        cls.source = create_planning_demo(cls.root/'demo')
        from stage1.gis import run
        cls.out = run(cls.source,False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def variant(self,name,**changes):
        config = json.loads(self.source.read_text()); config.update(output_dir=name,**changes)
        path = self.source.parent/(name+'.json'); path.write_text(json.dumps(config)); return path

    def test_minimum_two_spatial_inputs_produce_honest_planning_outputs(self):
        from stage1.gis import run
        path = self.variant('minimal',evidence=[],ownership=None,planning={})
        out = run(path,False)
        with sqlite3.connect(out/'stage1.gpkg') as db:
            self.assertGreater(db.execute('SELECT count(*) FROM planning_action_areas').fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM planning_opportunities WHERE status='ADMISSIBLE'").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM planning_opportunities WHERE opportunity_class != 'SURFACE_UNKNOWN'").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT DISTINCT owner_class FROM ownership").fetchall(),[('unknown',)])
        self.assertTrue((out/'report.html').exists())

    def test_unknown_surface_and_prohibitions_survive_mapping(self):
        with sqlite3.connect(self.out/'stage1.gpkg') as db:
            self.assertGreater(db.execute("SELECT count(*) FROM planning_opportunities WHERE opportunity_class='SURFACE_UNKNOWN'").fetchone()[0],0)
            self.assertGreater(db.execute("SELECT count(*) FROM planning_opportunities WHERE infiltration_status='FAIL' AND opportunity_class='INVESTIGATE'").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM planning_opportunities WHERE status='ADMISSIBLE'").fetchone()[0],0)

    def test_simple_exclusion_layer_blocks_intersecting_infiltration_only(self):
        from stage1.gis import run
        path = self.variant('simple-exclusion',evidence=[],planning={'restrictions':{
            'path':'inputs/synthetic.gpkg','layer':'planning_constraints','class_field':'protection_zone',
            'mapping':{'II':'infiltration_excluded'}}})
        out = run(path,False)
        with sqlite3.connect(out/'stage1.gpkg') as db:
            self.assertGreater(db.execute("SELECT count(*) FROM groundwater_screen WHERE status='FAIL'").fetchone()[0],0)
            self.assertGreater(db.execute("SELECT count(*) FROM groundwater_screen WHERE status='CONDITIONAL'").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM groundwater_screen WHERE status='ADMISSIBLE'").fetchone()[0],0)
            self.assertGreater(db.execute("SELECT count(*) FROM decision_audit WHERE rule_id='PL_KNOWN_INFILTRATION_EXCLUSION'").fetchone()[0],0)

    def test_no_need_run_still_has_empty_registers_and_unknown_depth(self):
        from stage1.gis import run
        path = self.variant('no-need',flood_threshold_m=100.)
        out = run(path,False)
        stats = json.loads((out/'planning_summary.json').read_text())
        self.assertEqual(stats['action_area_count'],0)
        self.assertEqual(stats['flood_need_area_m2'],0)
        self.assertGreater(stats['flood_unknown_area_m2'],0)
        self.assertTrue((out/'planning_shortlist.csv').read_text().startswith('action_id,'))
        self.assertEqual(len((out/'action_membership.csv').read_text().splitlines()),1)

    def test_conflicting_heat_classes_are_unknown_not_priority_credit(self):
        from qgis.core import QgsCoordinateReferenceSystem,QgsGeometry,QgsRectangle
        from stage1.gis import memory_layer,write_layer,run
        gpkg = self.source.parent/'inputs/heat-conflict.gpkg'
        geom = QgsGeometry.fromRect(QgsRectangle(360000,5639800,360240,5640000))
        records = [({'class':'HOT'},geom),({'class':'UNMAPPED'},geom)]
        write_layer(gpkg,memory_layer('heat',records,QgsCoordinateReferenceSystem('EPSG:25832')),'heat',first=True)
        path = self.variant('heat-conflict',planning={'heat':{'path':'inputs/heat-conflict.gpkg','layer':'heat','class_field':'class','mapping':{'HOT':'priority'}}})
        out = run(path,False)
        with sqlite3.connect(out/'stage1.gpkg') as db:
            self.assertEqual(db.execute('SELECT DISTINCT heat_priority_fraction,heat_unknown_fraction FROM planning_action_areas').fetchall(),[(0.,1.)])

    def test_uncovered_flood_extent_is_clickable_unknown(self):
        from qgis.core import QgsCoordinateReferenceSystem,QgsGeometry,QgsRectangle
        from stage1.gis import memory_layer,write_layer,run
        gpkg = self.source.parent/'inputs/extended.gpkg'
        geom = QgsGeometry.fromRect(QgsRectangle(360000,5639800,360260,5640000))
        write_layer(gpkg,memory_layer('area',[({'id':'extended'},geom)],QgsCoordinateReferenceSystem('EPSG:25832')),'area',first=True)
        path = self.variant('extended',study_area={'path':'inputs/extended.gpkg','layer':'area'},
                            raster_evidence=[{'path':'inputs/flood_cm.tif','field':'surface_elevation_m','units':'cm'}])
        out = run(path,False)
        with sqlite3.connect(out/'stage1.gpkg') as db:
            row = db.execute("SELECT status,area_m2 FROM intervention_need WHERE unit_id='UNMAPPED_FLOOD_COVERAGE'").fetchone()
            self.assertEqual(row,('UNKNOWN',4000.))
        import csv
        with (out/'evidence_snapshot.csv').open() as file:
            unknown = next(r for r in csv.DictReader(file) if r['unit_id']=='UNMAPPED_FLOOD_COVERAGE')
        self.assertEqual(unknown['surface_elevation_m'],'')

    def test_area_and_reference_registers_reconcile(self):
        data = json.loads((self.out/'planning_summary.json').read_text())
        with sqlite3.connect(self.out/'stage1.gpkg') as db:
            area = db.execute("SELECT sum(area_m2) FROM intervention_need WHERE status='YES'").fetchone()[0]
            action = db.execute('SELECT sum(area_m2) FROM planning_action_areas').fetchone()[0]
            self.assertAlmostEqual(area,action)
            self.assertAlmostEqual(area,data['flood_need_area_m2'])
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute("SELECT count(*) FROM planning_opportunities WHERE explanation IS NULL OR reference IS NULL OR next_action IS NULL").fetchone()[0],0)
        manifest = json.loads((self.out/'run_manifest.json').read_text())
        self.assertIn('planning.surfaces',[row['role'] for row in manifest['inputs']])
        self.assertIn('planning.heat',[row['role'] for row in manifest['inputs']])

    def test_preparation_keeps_planning_layers_and_category_mapping(self):
        from stage1.gis import run
        from stage1.preflight import inspect_config
        path = self.variant('prepared',preparation={'enabled':True})
        self.assertTrue(inspect_config(path).ok)
        out = run(path,False)
        config = json.loads((out/'resolved_config.json').read_text())
        self.assertTrue(Path(config['planning']['surfaces']['path']).is_file())
        with sqlite3.connect(out/'stage1.gpkg') as db:
            self.assertGreater(db.execute("SELECT count(*) FROM planning_opportunities WHERE opportunity_class='INVESTIGATE'").fetchone()[0],0)

    def test_registered_muriel_also_runs_in_planning_mode(self):
        from stage1.demo import create_muriel_demo
        from stage1.gis import run
        source = create_muriel_demo(self.root/'muriel'); config = json.loads(source.read_text()); config['mode']='planning';source.write_text(json.dumps(config))
        out = run(source,False)
        with sqlite3.connect(out/'stage1.gpkg') as db:
            self.assertGreater(db.execute('SELECT count(*) FROM muriel_priority').fetchone()[0],0)
            self.assertGreater(db.execute("SELECT count(*) FROM muriel_priority WHERE planning_class='PROTECT_RETENTION'").fetchone()[0],0)

    def test_action_areas_edge_connectivity_threshold_and_unknown_boundary(self):
        from qgis.core import QgsGeometry,QgsRectangle
        from stage1.planning_gis import action_areas
        def box(x,y): return QgsGeometry.fromRect(QgsRectangle(x,y,x+1,y+1))
        units = [dict(geometry=box(x,y),attrs={'unit_id':str(i),'flood_depth_m':d}) for i,(x,y,d) in enumerate([(1,1,.1),(2,1,.2),(3,2,.4),(0,1,None)])]
        aoi = QgsGeometry.fromRect(QgsRectangle(0,0,5,5))
        areas, membership = action_areas(units,aoi,.1)
        self.assertEqual(len(areas),2)
        self.assertEqual(sum(a['area_m2'] for a,_ in areas),3)
        self.assertEqual(set(membership),{'0','1','2'})
        self.assertTrue(all(a['extent_incomplete'] for a,_ in areas))
        higher,_ = action_areas(units,aoi,.3)
        self.assertEqual(len(higher),1)

    def test_default_panel_is_planning_and_hides_design_register(self):
        from stage1.planning_gui import PlanningDialog
        dialog = PlanningDialog(); dialog.show(); self.app.processEvents()
        self.assertEqual(dialog.mode.currentData(),'planning')
        self.assertFalse(dialog.designs.isVisible())
        self.assertIn('Optional planning',dialog.tabs.tabText(1))
        dialog.mode.setCurrentIndex(1); self.app.processEvents()
        self.assertTrue(dialog.designs.isVisible())
        self.assertIn('MURIEL',dialog.tabs.tabText(1))
        dialog.close()
