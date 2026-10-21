"""GIS preparation must preserve evidence, IDs, unknowns and original files."""
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')


@unittest.skipUnless(importlib.util.find_spec('qgis'),'Use QGIS Python')
class PreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from qgis.core import QgsApplication
        cls.app=QgsApplication.instance() or QgsApplication([],False);cls.app.initQgis()

    def setUp(self):
        from osgeo import gdal,ogr,osr
        import numpy as np
        self.temp=tempfile.TemporaryDirectory(prefix='nbs-preparation-');self.root=Path(self.temp.name)
        self.srs=osr.SpatialReference();self.srs.ImportFromEPSG(25832)
        self.srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        self.raster=self.root/'depth.tif'
        ds=gdal.GetDriverByName('GTiff').Create(str(self.raster),6,6,1,gdal.GDT_Float32)
        ds.SetProjection(self.srs.ExportToWkt());ds.SetGeoTransform((360000,10,0,5640000,0,-10))
        values=np.arange(36,dtype='float32').reshape(6,6);values[2,2]=-9999
        ds.GetRasterBand(1).WriteArray(values);ds.GetRasterBand(1).SetNoDataValue(-9999);ds=None
        self.vector=self.root/'boundary.gpkg'
        ds=ogr.GetDriverByName('GPKG').CreateDataSource(str(self.vector));layer=ds.CreateLayer('boundary',srs=self.srs,geom_type=ogr.wkbPolygon)
        feature=ogr.Feature(layer.GetLayerDefn());feature.SetGeometry(ogr.CreateGeometryFromWkt('POLYGON ((360010 5639950,360050 5639950,360050 5639990,360010 5639990,360010 5639950))'));layer.CreateFeature(feature);feature=None;layer=None;ds=None

    def tearDown(self):self.temp.cleanup()

    def job(self):
        return {'study_area':{'path':str(self.vector),'layer':'boundary'},'output_dir':str(self.root/'prepared'),
                'target_crs':'EPSG:25832','grid':{'master':{'path':str(self.raster)}},
                'datasets':[{'id':'depth','path':str(self.raster),'type':'raster','kind':'flood_depth'}]}

    def shape(self,with_crs=True):
        from osgeo import ogr
        path=self.root/'bare.shp';ds=ogr.GetDriverByName('ESRI Shapefile').CreateDataSource(str(path))
        layer=ds.CreateLayer('bare',srs=self.srs if with_crs else None,geom_type=ogr.wkbPolygon)
        feature=ogr.Feature(layer.GetLayerDefn());feature.SetGeometry(ogr.CreateGeometryFromWkt('POLYGON ((360010 5639950,360050 5639950,360050 5639990,360010 5639990,360010 5639950))'));layer.CreateFeature(feature);feature=None;layer=None;ds=None
        return path

    def test_native_grid_clip_preserves_values_offset_and_unknown(self):
        from stage1.preparation import prepare
        from osgeo import gdal
        import numpy as np
        out=prepare(self.job());manifest=json.loads((out/'preparation_manifest.json').read_text())
        self.assertEqual(manifest['grid']['master_index_offset'],[1,1]);self.assertTrue(manifest['grid']['native_master_grid_preserved'])
        ds=gdal.Open(str(out/'rasters/depth.tif'));values=ds.ReadAsArray()
        self.assertEqual(values.shape,(4,4));self.assertTrue(math.isnan(values[1,1]));self.assertEqual(values[0,0],7)
        self.assertTrue(np.isnan(ds.GetRasterBand(1).GetNoDataValue()))

    def test_categorical_classes_never_interpolated(self):
        from stage1.preparation import prepare
        from osgeo import gdal
        import numpy as np
        job=self.job();job['grid']['cell_size_m']=5;job['datasets'][0].update(kind='categorical')
        out=prepare(job);ds=gdal.Open(str(out/'rasters/depth.tif'));values=ds.ReadAsArray();finite=values[np.isfinite(values)]
        self.assertTrue(np.all(finite==np.floor(finite)))

    def test_bilinear_categorical_rejected_without_partial_folder(self):
        from stage1.preparation import prepare
        job=self.job();job['datasets'][0].update(kind='categorical',resampling='bilinear')
        with self.assertRaisesRegex(ValueError,'categorical'):prepare(job)
        self.assertFalse((self.root/'prepared').exists())

    def test_flood_resolution_change_requires_reference(self):
        from stage1.preparation import prepare
        job=self.job();job['grid']['cell_size_m']=20
        with self.assertRaisesRegex(ValueError,'resampling_evidence_ref'):prepare(job)

    def test_flood_phase_change_requires_reference(self):
        from stage1.preparation import prepare
        job=self.job();job['grid']['origin']=[360005,5640005]
        with self.assertRaisesRegex(ValueError,'resampling_evidence_ref'):prepare(job)

    def test_max_downsampling_is_explicitly_recorded(self):
        from stage1.preparation import prepare
        job=self.job();job['grid']['cell_size_m']=20;job['datasets'][0].update(resampling='max',resampling_evidence_ref='Reviewed conservative screening aggregation')
        out=prepare(job);record=json.loads((out/'preparation_manifest.json').read_text())['datasets'][0]
        self.assertEqual(record['resampling'],'max');self.assertTrue(record['grid_changed'])

    def test_missing_source_crs_is_not_guessed(self):
        from stage1.preparation import prepare
        path=self.shape(False);job=self.job();job['study_area']={'path':str(path)}
        with self.assertRaisesRegex(ValueError,'missing CRS'):prepare(job)
        self.assertFalse((self.root/'prepared').exists())

    def test_confirmed_crs_and_index_restoration_preserve_original(self):
        from stage1.preparation import prepare
        from stage1.inventory import file_hash
        path=self.shape(False);path.with_suffix('.shx').unlink();before=file_hash(path)
        job=self.job();job['study_area']={'path':str(path),'source_crs':'EPSG:25832','crs_evidence_ref':'Authoritative export record'}
        out=prepare(job);manifest=json.loads((out/'preparation_manifest.json').read_text())
        self.assertEqual(manifest['study_area']['crs']['action'],'assign_missing')
        self.assertEqual(file_hash(path),before);self.assertFalse(path.with_suffix('.shx').exists())

    def test_crs_override_requires_evidence(self):
        from stage1.preparation import prepare
        path=self.shape(False);job=self.job();job['study_area']={'path':str(path),'source_crs':'EPSG:25832'}
        with self.assertRaisesRegex(ValueError,'crs_evidence_ref'):prepare(job)

    def test_missing_attributes_require_geometry_only_decision(self):
        from stage1.preparation import prepare
        path=self.shape();path.with_suffix('.dbf').unlink();job=self.job();job['study_area']={'path':str(path)}
        with self.assertRaisesRegex(ValueError,'missing .dbf'):prepare(job)
        job['study_area']['allow_geometry_only']=True
        out=prepare(job);self.assertTrue(json.loads((out/'preparation_manifest.json').read_text())['study_area']['geometry_only'])

    def test_inventory_reports_duplicate_and_sidecars_without_repair(self):
        from stage1.inventory import inspect_paths
        path=self.shape(False);path.with_suffix('.shx').unlink()
        rows=inspect_paths([path,path])
        self.assertIn('.shx',rows[0]['missing_components']);self.assertIn('duplicate_of',rows[1])
        self.assertFalse(path.with_suffix('.shx').exists())

    def test_reprojection_and_attribute_and_z_preservation(self):
        from osgeo import ogr,osr
        from stage1.preparation import prepare
        path=self.root/'points.gpkg';source=osr.SpatialReference();source.ImportFromEPSG(4326);source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        transform=osr.CoordinateTransformation(self.srs,source);x,y,z=transform.TransformPoint(360020,5639970,123.45)
        ds=ogr.GetDriverByName('GPKG').CreateDataSource(str(path));layer=ds.CreateLayer('points',srs=source,geom_type=ogr.wkbPoint25D);layer.CreateField(ogr.FieldDefn('evidence_ref',ogr.OFTString))
        feature=ogr.Feature(layer.GetLayerDefn());feature.SetField('evidence_ref','Actual evidence stays unchanged');geom=ogr.Geometry(ogr.wkbPoint25D);geom.AddPoint(x,y,z);feature.SetGeometry(geom);layer.CreateFeature(feature);feature=None;layer=None;ds=None
        job=self.job();job['datasets']=[{'id':'points','path':str(path),'layer':'points'}]
        out=prepare(job);ds=ogr.Open(str(out/'prepared.gpkg'));f=next(iter(ds.GetLayerByName('points')));p=f.GetGeometryRef().GetGeometryRef(0)
        self.assertAlmostEqual(p.GetX(),360020,places=3);self.assertAlmostEqual(p.GetZ(),123.45,places=5);self.assertEqual(f['evidence_ref'],'Actual evidence stays unchanged')

    def test_cancellation_cleans_output(self):
        from stage1.preparation import prepare
        from stage1.runtime import RunCancelled
        cancel=[False]
        def progress(p,m):
            if p>=82:cancel[0]=True
        with self.assertRaises(RunCancelled):prepare(self.job(),progress,lambda:cancel[0])
        self.assertFalse((self.root/'prepared').exists());self.assertEqual(list(self.root.glob('.prepared_preparing_*')),[])

    def test_integrated_crop_keeps_id_evidence_joins(self):
        from stage1.configuration import starter_config
        from stage1.gis import run
        from osgeo import ogr
        import sqlite3
        config=starter_config({'path':str(self.raster),'type':'raster','units':'cm'}, {'path':str(self.vector),'layer':'boundary'},self.root/'results',scenario='TEST_EVENT',crs='EPSG:25832')
        config['designs']=['green_roof'];config['muriel']['enabled']=False;config['preparation']={'enabled':True}
        source=ogr.GetDriverByName('GPKG').CreateDataSource(str(self.root/'evidence.gpkg'))
        layer=source.CreateLayer('evidence',srs=self.srs,geom_type=ogr.wkbPolygon)
        for name in ('unit_id','land_type'):layer.CreateField(ogr.FieldDefn(name,ogr.OFTString))
        feature=ogr.Feature(layer.GetLayerDefn());feature.SetField('unit_id','r0000001_c0000001');feature.SetField('land_type','roof')
        feature.SetGeometry(ogr.CreateGeometryFromWkt('POLYGON ((360010 5639980,360020 5639980,360020 5639990,360010 5639990,360010 5639980))'));layer.CreateFeature(feature);feature=None;layer=None;source=None
        config['evidence']=[{'path':str(self.root/'evidence.gpkg'),'layer':'evidence','join':'id'}]
        path=self.root/'run.json';path.write_text(json.dumps(config))
        out=run(path,False)
        with sqlite3.connect(out/'stage1.gpkg') as db:
            ids={r[0] for r in db.execute('SELECT unit_id FROM intervention_need')}
            self.assertIn('r0000001_c0000001',ids);self.assertNotIn('r0000000_c0000000',ids)
            self.assertEqual(db.execute("SELECT status FROM decision_audit WHERE unit_id='r0000001_c0000001' AND rule_id='land_type'").fetchone()[0],'ADMISSIBLE')
        db.close()
        prepared=json.loads((self.root/'results_prepared/prepared_run.json').read_text())
        self.assertEqual(prepared['unit_id_grid_offset'],[1,1]);self.assertFalse(prepared['preparation']['enabled'])

    def test_wrong_declared_crs_can_be_replaced_with_evidence(self):
        from stage1.preparation import prepare
        from osgeo import osr
        path=self.shape();wrong=osr.SpatialReference();wrong.ImportFromEPSG(4326);path.with_suffix('.prj').write_text(wrong.ExportToWkt())
        job=self.job();job['study_area']={'path':str(path),'source_crs':'EPSG:25832','crs_evidence_ref':'Provider confirmed the incorrect label'}
        out=prepare(job);manifest=json.loads((out/'preparation_manifest.json').read_text())
        self.assertEqual(manifest['study_area']['crs']['action'],'replace_declared')

    def test_invalid_geometry_repair_is_explicit_and_audited(self):
        from stage1.preparation import prepare
        from osgeo import ogr
        path=self.root/'invalid.gpkg';ds=ogr.GetDriverByName('GPKG').CreateDataSource(str(path));layer=ds.CreateLayer('invalid',srs=self.srs,geom_type=ogr.wkbPolygon)
        feature=ogr.Feature(layer.GetLayerDefn());feature.SetGeometry(ogr.CreateGeometryFromWkt('POLYGON ((360020 5639960,360040 5639980,360020 5639980,360040 5639960,360020 5639960))'));layer.CreateFeature(feature);feature=None;layer=None;ds=None
        job=self.job();job['datasets']=[{'id':'invalid','path':str(path),'layer':'invalid'}]
        with self.assertRaisesRegex(ValueError,'invalid geometry'):prepare(job)
        job['datasets'][0]['repair_invalid']=True
        out=prepare(job);manifest=json.loads((out/'preparation_manifest.json').read_text())
        self.assertTrue(manifest['repairs'][0]['review_required']);self.assertTrue((out/'geometry_repairs.csv').exists())

    def test_prepared_review_project_is_portable(self):
        from stage1.preparation import prepare
        from qgis.core import QgsProject
        import shutil
        out=prepare(self.job());relocated=self.root/'relocated';shutil.copytree(out,relocated)
        project=QgsProject();self.assertTrue(project.read(str(relocated/'prepared_inputs.qgz')))
        self.assertTrue(all(l.isValid() and str(relocated) in l.source() for l in project.mapLayers().values()))

    def test_vector_flood_preparation_preserves_muriel_results(self):
        from stage1.demo import create_muriel_demo
        from stage1.gis import run
        source=create_muriel_demo(self.root/'muriel');config=json.loads(source.read_text());config.update(preparation={'enabled':True},designs=['green_roof'])
        source.write_text(json.dumps(config));out=run(source,False)
        counts=json.loads((out/'muriel_summary.json').read_text())['planning_counts']
        self.assertEqual(len(counts),7);self.assertEqual(counts['PROTECT_RETENTION'],1);self.assertEqual(counts['RETROFIT_CANDIDATE'],1)

    def test_preparation_dialog_builds_and_executes_job_without_guessing_crs(self):
        from stage1.preparation_gui import PreparationDialog
        dialog=PreparationDialog();dialog.boundary.setText(str(self.vector));dialog.boundary_layer.setText('boundary');dialog.master.setText(str(self.raster));dialog.folder.setText(str(self.root/'gui'))
        dialog.add_path(str(self.raster));job=dialog.job()
        self.assertNotIn('source_crs',job['study_area']);self.assertNotIn('cell_size_m',job['grid'])
        dialog.execute(job)
        self.assertTrue((dialog.output/'prepared_inputs.qgz').exists());dialog.close()

    def test_scaled_raster_needs_documented_physical_conversion(self):
        from stage1.preparation import prepare
        from osgeo import gdal
        source=gdal.Open(str(self.raster),gdal.GA_Update);source.GetRasterBand(1).SetScale(.01);source=None
        with self.assertRaisesRegex(ValueError,'scale/offset'):prepare(self.job())

    def test_flood_unit_conflict_is_not_silently_accepted(self):
        from stage1.preparation import prepare
        from osgeo import gdal
        source=gdal.Open(str(self.raster),gdal.GA_Update);source.GetRasterBand(1).SetUnitType('m');source=None
        job=self.job();job['datasets'][0]['units']='cm'
        with self.assertRaisesRegex(ValueError,'units disagree'):prepare(job)

    def test_partial_boundary_cells_keep_source_depth(self):
        from stage1.preparation import prepare
        from osgeo import gdal,ogr
        source=ogr.Open(str(self.vector),1);layer=source.GetLayer(0);feature=layer.GetFeature(1)
        feature.SetGeometry(ogr.CreateGeometryFromWkt('POLYGON ((360016 5639950,360044 5639950,360044 5639990,360016 5639990,360016 5639950))'));layer.SetFeature(feature);feature=None;layer=None;source=None
        out=prepare(self.job());raster=gdal.Open(str(out/'rasters/depth.tif'))
        self.assertEqual(raster.ReadAsArray()[0,0],7)

    def test_regridding_cannot_reuse_old_combination_unit_ids(self):
        from stage1.configuration import starter_config
        from stage1.preparation import prepare_run
        config=starter_config({'path':str(self.raster),'type':'raster','units':'cm','resampling_evidence_ref':'Reviewed grid change'}, {'path':str(self.vector),'layer':'boundary'},self.root/'changed',scenario='TEST_EVENT',crs='EPSG:25832')
        config['preparation']={'enabled':True,'grid':{'cell_size_m':20}}
        config['combinations']=[{'id':'old_grid_portfolio','modules':[]}]
        source=self.root/'changed.json';source.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError,'combination unit IDs'):prepare_run(source)
