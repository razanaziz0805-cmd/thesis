"""Real spatial operations and integrated MURIEL results."""
from contextlib import closing
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')


@unittest.skipUnless(importlib.util.find_spec('qgis'), 'Run with the QGIS Python interpreter')
class MurielGISTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from qgis.core import QgsApplication,QgsCoordinateReferenceSystem
        from stage1.demo import create_muriel_demo
        from stage1.gis import run,resolve_config,read_units
        from osgeo import gdal
        cls.app=QgsApplication.instance() or QgsApplication([],False)
        cls.app.initQgis()
        cls.tmp=tempfile.TemporaryDirectory(prefix='muriel-tests-')
        cls.root=Path(cls.tmp.name)
        cls.path=create_muriel_demo(cls.root/'demo')
        c=json.loads(cls.path.read_text());c['designs']=['green_roof','lined_detention']
        cls.path.write_text(json.dumps(c))
        cls.errors=[]
        gdal.PushErrorHandler(lambda level,code,message:cls.errors.append(message) if level>=gdal.CE_Failure else None)
        try: cls.out=run(cls.path,export_maps=False)
        finally: gdal.PopErrorHandler()
        cls.config=resolve_config(cls.path)
        cls.crs=QgsCoordinateReferenceSystem('EPSG:25832')
        cls.units,cls.aoi,_=read_units(cls.config,cls.crs)
        cls.groundwater=[({'unit_id':u['attrs']['unit_id'],'status':'CONDITIONAL'},u['geometry']) for u in cls.units]

    @classmethod
    def tearDownClass(cls):
        from qgis.core import QgsProject
        QgsProject.instance().clear()
        cls.tmp.cleanup()

    def db(self):return closing(sqlite3.connect(self.out/'stage1.gpkg'))

    def screen(self,config=None):
        from stage1.muriel import screen
        return screen(self.units,self.aoi,self.crs,config or self.config,self.groundwater)

    def test_all_seven_expected_planning_outcomes(self):
        with self.db() as db:
            classes=dict(db.execute('SELECT planning_class,count(*) FROM muriel_priority GROUP BY planning_class'))
            self.assertEqual(classes,{'PROTECT_RETENTION':1,'RETROFIT_CANDIDATE':1,'ROUTING_INVESTIGATION':1,'NO_DESTINATION':1,'OUTSIDE_PRIORITY':1,'BELOW_SCREEN':1,'ROUTE_UNSUITABLE':1})

    def test_grid_pieces_dissolved_before_area_test(self):
        with self.db() as db:
            area,depth,overlap,members=db.execute("SELECT area_m2,max_depth_m,overlap_percent,source_unit_ids FROM muriel_priority WHERE planning_class='PROTECT_RETENTION'").fetchone()
            self.assertEqual(area,3200)
            self.assertAlmostEqual(depth,.45)
            self.assertEqual(overlap,75)
            self.assertEqual(len(json.loads(members)),4)

    def test_source_mask_preserves_thirty_cm_and_nodata_decisions(self):
        with self.db() as db:
            result=dict(db.execute("SELECT unit_id,mask_class FROM muriel_source_mask"))
            self.assertEqual(result['depth_exact'],'DEPTH_EXCLUDED')
            self.assertEqual(result['shallow_apron'],'DEPTH_EXCLUDED')
            self.assertEqual(result['nodata'],'DEPTH_UNKNOWN')

    def test_source_and_route_rules_have_citations_and_closures(self):
        with self.db() as db:
            self.assertGreater(db.execute("SELECT count(*) FROM decision_audit WHERE design LIKE 'MURIEL%'").fetchone()[0],70)
            self.assertEqual(db.execute("SELECT count(*) FROM decision_audit WHERE design LIKE 'MURIEL%' AND (citation='' OR source_locator='' OR closure='' OR evidence_ref='')").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM decision_audit WHERE source_id='MURIEL' AND source_url=''").fetchone()[0],0)

    def test_proximity_is_not_verified_route(self):
        with self.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM muriel_connections WHERE line_kind='VERIFIED_ROUTE'").fetchone()[0],1)
            self.assertGreater(db.execute("SELECT count(*) FROM muriel_connections WHERE line_kind='PROXIMITY_ONLY' AND status='CONDITIONAL'").fetchone()[0],0)

    def test_no_gdal_failures_and_provenance_complete(self):
        self.assertEqual(self.errors,[])
        manifest=json.loads((self.out/'run_manifest.json').read_text())
        self.assertTrue(manifest['muriel']['enabled'])
        self.assertEqual(manifest['muriel']['thresholds']['footprint_mode'],'depth_mask')
        self.assertEqual(len([p for p in manifest['inputs'] if p['role'].startswith('muriel_')]),5)

    def test_footprint_modes_change_the_registered_area(self):
        from stage1.muriel import flood_hotspots
        masked=flood_hotspots(self.units,self.aoi)
        maximum=flood_hotspots(self.units,self.aoi,{'footprint_mode':'inundation_maximum'})
        a=next(h for h in masked if 'protect_0' in h['source_unit_ids'])
        b=next(h for h in maximum if 'protect_0' in h['source_unit_ids'])
        self.assertEqual(a['area_m2'],3200)
        self.assertEqual(b['area_m2'],4000)

    def test_hotspot_ids_stable_under_input_order(self):
        from stage1.muriel import flood_hotspots
        normal=flood_hotspots(self.units,self.aoi)
        reversed_=flood_hotspots(list(reversed(self.units)),self.aoi)
        self.assertEqual([h['hotspot_id'] for h in normal],[h['hotspot_id'] for h in reversed_])

    def test_corner_contacts_separate_and_edges_merge(self):
        from qgis.core import QgsGeometry,QgsRectangle
        from stage1.muriel import flood_hotspots
        def unit(i,x,y):return {'attrs':{'unit_id':str(i),'flood_depth_m':1},'geometry':QgsGeometry.fromRect(QgsRectangle(x,y,x+1,y+1))}
        aoi=QgsGeometry.fromRect(QgsRectangle(-1,-1,5,5))
        self.assertEqual(len(flood_hotspots([unit(1,0,0),unit(2,1,1)],aoi)),2)
        self.assertEqual(len(flood_hotspots([unit(1,0,0),unit(2,1,0)],aoi)),1)

    def test_uncovered_vector_extent_marks_partial_footprint(self):
        from qgis.core import QgsGeometry,QgsRectangle
        from stage1.muriel import flood_hotspots
        aoi=QgsGeometry.fromRect(QgsRectangle(0,0,100,100))
        unit={'attrs':{'unit_id':'partial','flood_depth_m':1},'geometry':QgsGeometry.fromRect(QgsRectangle(20,20,60,60))}
        self.assertTrue(flood_hotspots([unit],aoi)[0]['boundary_incomplete'])

    def test_missing_roads_does_not_prove_nonroad_destination(self):
        config=copy.deepcopy(self.config);config['muriel']['roads']['coverage_complete']=False
        result=self.screen(config)
        self.assertEqual(result['destinations'],[])
        self.assertTrue(all(a['planning_class']=='EVIDENCE_GAP' for a,_ in result['priority'] if a['area_m2']>2000 and 'no_receptor' not in a['source_unit_ids']))
        self.assertEqual(next(a['planning_class'] for a,_ in result['priority'] if 'no_receptor' in a['source_unit_ids']),'OUTSIDE_PRIORITY')

    def test_roads_subtracted_before_retention_overlap(self):
        from qgis.core import QgsGeometry,QgsRectangle
        from stage1.gis import memory_layer,write_layer
        config=copy.deepcopy(self.config)
        path=self.root/'road-cut.gpkg'
        road=QgsGeometry.fromRect(QgsRectangle(360100,5639100,360140,5639140))
        write_layer(path,memory_layer('roads',[({'id':'newroad'},road)],self.crs),'roads',first=True)
        config['muriel']['roads']['path']=str(path)
        result=self.screen(config)
        record=next(a for a,_ in result['priority'] if 'protect_0' in a['source_unit_ids'])
        self.assertAlmostEqual(record['overlap_percent'],25.)
        self.assertNotEqual(record['planning_class'],'PROTECT_RETENTION')

    def test_public_class_filter_prevents_private_destination(self):
        from stage1.gis import memory_layer,write_layer,load_vector
        config=copy.deepcopy(self.config)
        original=load_vector(config['muriel']['municipal_land'],self.crs)
        data=[({**{k:v for k,v in a.items() if k!='fid'},'owner_class':'PRIVATE' if a.get('destination_id')=='S_PROTECT' else 'CITY'},g) for g,a in original]
        path=self.root/'ownership-filter.gpkg'
        write_layer(path,memory_layer('ownership',data,self.crs),'ownership',first=True)
        config['muriel']['municipal_land'].update(path=str(path),layer='ownership',class_field='owner_class',municipal_values=['CITY'])
        result=self.screen(config)
        self.assertNotIn('S_PROTECT',[a['destination_id'] for a,_ in result['destinations']])

    def test_wrong_route_direction_does_not_pass(self):
        from stage1.gis import load_vector,memory_layer,write_layer
        config=copy.deepcopy(self.config)
        original=load_vector(config['muriel']['routes'],self.crs)
        data=[]
        for geom,a in original:
            if a['destination_id']=='S_RETROFIT':
                from qgis.core import QgsGeometry
                geom=QgsGeometry.fromMultiPolylineXY([list(reversed(points)) for points in reversed(geom.asMultiPolyline())])
            data.append(({k:v for k,v in a.items() if k!='fid'},geom))
        path=self.root/'reverse-route.gpkg'
        write_layer(path,memory_layer('routes',data,self.crs,geometry_type='MultiLineString'),'routes',first=True)
        config['muriel']['routes']['path']=str(path)
        result=self.screen(config)
        row=next(a for a,_ in result['priority'] if '"retrofit"' in a['source_unit_ids'])
        self.assertEqual(row['planning_class'],'ROUTE_UNSUITABLE')

    def test_empty_and_missing_inputs_remain_conditional(self):
        config=copy.deepcopy(self.config)
        config['muriel']={'enabled':True}
        result=self.screen(config)
        self.assertEqual(result['destinations'],[])
        self.assertTrue(all(a['planning_class']=='EVIDENCE_GAP' for a,_ in result['priority'] if a['area_m2']>2000))

    def test_saved_project_relocates_with_all_muriel_layers(self):
        from qgis.core import QgsProject
        dest=self.root/'moved';dest.mkdir()
        for name in ['stage1.qgz','stage1.gpkg']:shutil.copy2(self.out/name,dest/name)
        project=QgsProject.instance();project.clear()
        self.assertTrue(project.read(str(dest/'stage1.qgz')))
        self.assertTrue(all(l.isValid() for l in project.mapLayers().values()))
        self.assertEqual(len([n for n in project.mapThemeCollection().mapThemes() if n.startswith('MURIEL')]),5)

    def test_out_of_radius_route_retained_without_conferring_eligibility(self):
        config=copy.deepcopy(self.config)
        config['muriel']['thresholds']['destination_distance_m']=5
        result=self.screen(config)
        retrofit=next(a for a,_ in result['priority'] if '"retrofit"' in a['source_unit_ids'])
        self.assertEqual(retrofit['planning_class'],'NO_DESTINATION')
        self.assertTrue(any(r['rule_id']=='MURIEL_ROUTE_PAIR_RADIUS' and r['status']=='FAIL' for r in result['audit']))

    def test_no_observed_deep_cells_still_has_source_mask_and_zero_count(self):
        config=copy.deepcopy(self.config)
        config['muriel']['thresholds']['min_max_depth_m']=1.
        config['muriel']['routes']=None
        result=self.screen(config)
        self.assertEqual(result['summary']['footprint_count'],0)
        self.assertEqual(len(result['source_mask']),len(self.units))
        self.assertEqual(result['priority'],[])

    def test_overlapping_private_claim_is_removed_from_city_land(self):
        from qgis.core import QgsGeometry,QgsRectangle
        from stage1.gis import memory_layer,write_layer,load_vector
        config=copy.deepcopy(self.config)
        original=load_vector(config['muriel']['municipal_land'],self.crs)
        data=[({**{k:v for k,v in a.items() if k!='fid'},'owner_class':'CITY'},g) for g,a in original]
        data.append(({'destination_id':'CONFLICT','owner_class':'PRIVATE'},QgsGeometry.fromRect(QgsRectangle(360100,5639100,360140,5639140))))
        path=self.root/'ownership-conflict.gpkg'
        write_layer(path,memory_layer('ownership',data,self.crs),'ownership',first=True)
        config['muriel']['municipal_land'].update(path=str(path),layer='ownership',class_field='owner_class',municipal_values=['CITY'])
        result=self.screen(config)
        d=next(a for a,_ in result['destinations'] if a['destination_id']=='S_PROTECT')
        self.assertEqual(d['eligible_area_m2'],800.)
