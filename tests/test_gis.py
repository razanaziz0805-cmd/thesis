"""Real PyQGIS/GDAL integration tests. Run with the QGIS Python interpreter."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
QGIS_AVAILABLE = importlib.util.find_spec('qgis') is not None


@unittest.skipUnless(QGIS_AVAILABLE, 'Requires the QGIS Python interpreter; run scripts/test.sh for full validation')
class GISTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from qgis.core import QgsApplication
        cls.app = QgsApplication.instance() or QgsApplication([], False)
        cls.app.initQgis()
        cls.tmp = tempfile.TemporaryDirectory(prefix='thesis-stage1-test-')
        cls.root = Path(cls.tmp.name)
        from stage1.demo import create_demo
        from stage1.gis import run
        cls.config_path = create_demo(cls.root / 'demo')
        cls.config = json.loads(cls.config_path.read_text())
        cls.config['designs'] = ['green_roof', 'tree_trench_lined', 'tree_trench_infiltration']
        cls.config_path.write_text(json.dumps(cls.config))
        from osgeo import gdal
        cls.gdal_errors = []
        gdal.PushErrorHandler(lambda level, code, message: cls.gdal_errors.append(message) if level >= gdal.CE_Failure else None)
        try:
            cls.out = run(cls.config_path, export_maps=False)
        finally:
            gdal.PopErrorHandler()

    @classmethod
    def tearDownClass(cls):
        from qgis.core import QgsProject
        QgsProject.instance().clear()
        cls.tmp.cleanup()

    def db(self):
        return closing(sqlite3.connect(self.out / 'stage1.gpkg'))

    def test_no_gdal_failure_during_generation(self):
        self.assertEqual(self.gdal_errors, [])

    def test_cm_conversion_threshold_and_nodata_survive(self):
        with self.db() as db:
            rows = dict(db.execute('SELECT unit_id,status FROM intervention_need WHERE unit_id LIKE "r0000000_c%"'))
            self.assertEqual(rows['r0000000_c0000000'], 'UNKNOWN')
            self.assertEqual(rows['r0000000_c0000001'], 'NO')
            self.assertEqual(rows['r0000000_c0000002'], 'YES')
            d = db.execute('SELECT flood_depth_m FROM intervention_need WHERE unit_id=?', ('r0000000_c0000002',)).fetchone()[0]
            self.assertAlmostEqual(d, .1)

    def test_analysis_units_and_audit_are_complete(self):
        with self.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM intervention_need').fetchone()[0], 120)
            self.assertEqual(db.execute('SELECT count(*) FROM nbs_opportunities').fetchone()[0], 360)
            self.assertGreater(db.execute('SELECT count(*) FROM decision_audit').fetchone()[0], 5000)
            self.assertEqual(db.execute('SELECT count(*) FROM decision_audit WHERE citation IS NULL OR responsible_party IS NULL OR closure IS NULL').fetchone()[0], 0)

    def test_groundwater_preliminary_never_admissible(self):
        with self.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM groundwater_screen WHERE status='ADMISSIBLE'").fetchone()[0], 0)

    def test_municipal_private_mixed_unknown_and_conflict_retained(self):
        with self.db() as db:
            statuses = {r[0] for r in db.execute('SELECT DISTINCT status FROM ownership')}
            self.assertTrue({'municipal', 'private', 'mixed', 'unknown', 'conflict', 'other_public'} <= statuses)
            a = db.execute('SELECT municipal_fraction,private_fraction FROM ownership WHERE unit_id=?', ('r0000000_c0000005',)).fetchone()
            self.assertAlmostEqual(a[0], .5)
            self.assertAlmostEqual(a[1], .5)

    def test_portfolio_decisions_are_distinct(self):
        with self.db() as db:
            results = dict(db.execute('SELECT combination_id,status FROM combinations'))
            self.assertEqual(results, {'roof_to_lined_tree': 'ADMISSIBLE', 'unverified_route': 'CONDITIONAL', 'source_double_counted': 'FAIL', 'prohibited_infiltration_member': 'FAIL'})

    def test_provenance_and_crs(self):
        with self.db() as db:
            self.assertEqual(db.execute("SELECT srs_id FROM gpkg_geometry_columns WHERE table_name='nbs_opportunities'").fetchone()[0], 25832)
        manifest = json.loads((self.out / 'run_manifest.json').read_text())
        self.assertTrue(manifest['demo'])
        self.assertTrue(all(len(r['sha256']) == 64 for r in manifest['inputs']))
        self.assertEqual(manifest['grid']['pixel_size_m'], [20, 20])

    def test_project_reopens_after_relocation(self):
        from qgis.core import QgsProject
        relocated = self.root / 'relocated'
        relocated.mkdir(exist_ok=True)
        shutil.copy2(self.out / 'stage1.qgz', relocated)
        shutil.copy2(self.out / 'stage1.gpkg', relocated)
        project = QgsProject.instance()
        project.clear()
        self.assertTrue(project.read(str(relocated / 'stage1.qgz')))
        self.assertTrue(all(l.isValid() for l in project.mapLayers().values()))
        self.assertTrue(all(str(relocated) in l.source() for l in project.mapLayers().values()))
        self.assertGreater(len(project.mapThemeCollection().mapThemes()), 5)

    def test_do_not_overwrite_previous_run(self):
        from stage1.gis import run
        with self.assertRaisesRegex(ValueError, 'already exists'):
            run(self.config_path, export_maps=False)

    def test_spatial_overlay_retains_tiny_known_prohibition(self):
        from qgis.core import QgsGeometry, QgsRectangle
        from stage1.gis import indexed, join_evidence
        unit = QgsGeometry.fromRect(QgsRectangle(0, 0, 100, 100))
        tiny = QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1))
        idx, records = indexed([(tiny, {'zone': 'II', 'clean': 0})])
        result = join_evidence(unit, idx, records, {'protection_zone': 'zone', 'receiving_ground_clean': 'clean'}, zone_priority=['I','II'])
        self.assertEqual(result, {'protection_zone': 'II', 'receiving_ground_clean': False})

    def test_aligned_raster_values_and_design_depth_are_derived_without_approval(self):
        from stage1.gis import derived_evidence, read_units, resolve_config
        from qgis.core import QgsCoordinateReferenceSystem
        config = resolve_config(self.config_path)
        crs = QgsCoordinateReferenceSystem(config['crs'])
        units, _, grid = read_units(config, crs)
        config['raster_evidence'] = [{'path': config['flood']['path'], 'field': 'surface_elevation_m', 'units': 'cm'}]
        config['derived_module_bases'] = [{'design': 'tree_trench_infiltration', 'surface_field': 'surface_elevation_m', 'base_depth_m': .02}]
        derived_evidence(config, units, grid, crs)
        by_id = {u['attrs']['unit_id']: u['attrs'] for u in units}
        self.assertIsNone(by_id['r0000000_c0000000']['surface_elevation_m'])
        self.assertAlmostEqual(by_id['r0000000_c0000002']['module_base_elevation_m__tree_trench_infiltration'], .08)
        self.assertNotIn('design_geometry_confirmed', by_id['r0000000_c0000002'])

    def test_misaligned_raster_is_rejected(self):
        from osgeo import gdal
        from stage1.gis import derived_evidence, read_units, resolve_config
        from qgis.core import QgsCoordinateReferenceSystem
        config = resolve_config(self.config_path)
        crs = QgsCoordinateReferenceSystem(config['crs'])
        units, _, grid = read_units(config, crs)
        path = self.root / 'shifted.tif'
        source = gdal.Open(config['flood']['path'])
        ds = gdal.GetDriverByName('GTiff').CreateCopy(str(path), source)
        gt = list(ds.GetGeoTransform()); gt[0] += 1
        ds.SetGeoTransform(gt)
        ds = source = None
        config['raster_evidence'] = [{'path': str(path), 'field': 'design_groundwater_elevation_m', 'units': 'm'}]
        with self.assertRaisesRegex(ValueError, 'must match the master-grid'):
            derived_evidence(config, units, grid, crs)

    def test_geometric_distance_requires_complete_inventory(self):
        from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry, QgsRectangle
        from stage1.gis import derived_evidence, memory_layer, write_layer
        crs = QgsCoordinateReferenceSystem('EPSG:25832')
        path = self.root / 'distance.gpkg'
        reference = QgsGeometry.fromRect(QgsRectangle(20, 0, 30, 10))
        write_layer(path, memory_layer('basements', [({'id': 'ref'}, reference)], crs), 'basements', first=True)
        units = [{'geometry': QgsGeometry.fromRect(QgsRectangle(0, 0, 10, 10)), 'attrs': {}}]
        spec = {'path': str(path), 'layer': 'basements', 'field': 'basement_distance_m', 'coverage_complete': True, 'evidence_ref': 'TEST_SURVEY'}
        config = {'distance_evidence': [spec]}
        derived_evidence(config, units, {}, crs)
        self.assertEqual(units[0]['attrs']['basement_distance_m'], 10.)
        spec['coverage_complete'] = False
        derived_evidence(config, units, {}, crs)
        self.assertIsNone(units[0]['attrs']['basement_distance_m'])

    def test_vector_flood_input_and_overlap_rejection(self):
        from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry, QgsRectangle
        from stage1.gis import read_units, memory_layer, write_layer, resolve_config
        config = resolve_config(self.config_path)
        crs = QgsCoordinateReferenceSystem(config['crs'])
        records = [({'unit_id': 'v1', 'depth_cm': 10}, QgsGeometry.fromRect(QgsRectangle(360000, 5639980, 360020, 5640000))),
                   ({'unit_id': 'v2', 'depth_cm': 9}, QgsGeometry.fromRect(QgsRectangle(360020, 5639980, 360040, 5640000)))]
        path = self.root / 'vector.gpkg'
        write_layer(path, memory_layer('flood', records, crs), 'flood', first=True)
        config['flood'] = {'path': str(path), 'type': 'vector', 'layer': 'flood', 'units': 'cm', 'depth_field': 'depth_cm', 'id_field': 'unit_id'}
        units, _, _ = read_units(config, crs)
        self.assertEqual(len(units), 2)
        self.assertAlmostEqual(units[0]['attrs']['flood_depth_m'], .1)
        records[1] = (records[1][0], records[0][1])
        overlap = self.root / 'overlap.gpkg'
        write_layer(overlap, memory_layer('flood', records, crs), 'flood', first=True)
        config['flood']['path'] = str(overlap)
        with self.assertRaisesRegex(ValueError, 'overlap'):
            read_units(config, crs)

    def test_processing_algorithm_runs_and_preserves_gui_project(self):
        import importlib.util
        from qgis.core import QgsProject, QgsProcessingContext, QgsProcessingFeedback, QgsVectorLayer
        spec = importlib.util.spec_from_file_location('qgis_stage1_processing', Path(__file__).resolve().parents[1] / 'scripts/qgis_stage1_processing.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        algorithm = module.NbsOpportunityStageOne()
        algorithm.initAlgorithm()
        config = dict(self.config)
        config.update(designs=['green_roof'], combinations=[], output_dir='processing_results')
        path = self.config_path.parent / 'processing.json'
        path.write_text(json.dumps(config))
        sentinel = QgsVectorLayer('Polygon?crs=EPSG:25832', 'UNSAVED_GUI_PROJECT_SENTINEL', 'memory')
        gui_project = QgsProject.instance()
        gui_project.addMapLayer(sentinel)
        sid = sentinel.id()
        context = QgsProcessingContext()
        result = algorithm.processAlgorithm({'REPOSITORY': str(Path(__file__).resolve().parents[1]), 'CONFIG': str(path), 'EXPORT_MAPS': False}, context, QgsProcessingFeedback())
        self.assertTrue(Path(result['PROJECT']).exists())
        self.assertIsNotNone(gui_project.mapLayer(sid))
        gui_project.removeMapLayer(sid)


if __name__ == '__main__':
    unittest.main()
