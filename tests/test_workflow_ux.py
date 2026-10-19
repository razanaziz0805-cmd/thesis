"""Meaningful regression checks for setup, cancellation and spatial optimisation."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from stage1.configuration import starter_config, structure_errors


class ConfigurationTests(unittest.TestCase):
    def test_collects_missing_inputs_together(self):
        errors=structure_errors({'designs':[]})
        self.assertGreaterEqual(len(errors),8)
        self.assertTrue(any('flood' in e for e in errors))
        self.assertTrue(any('study_area' in e for e in errors))

    def test_malformed_containers_are_reported(self):
        config=starter_config({'path':'f.tif','type':'raster','units':'cm'},{'path':'a.gpkg'})
        config.update(evidence='invalid',muriel='invalid')
        self.assertGreaterEqual(len(structure_errors(config)),2)

    def test_duplicate_designs_are_rejected(self):
        config=starter_config({'path':'f.tif','type':'raster','units':'cm'},{'path':'a.gpkg'})
        config['designs']=['green_roof','green_roof']
        self.assertTrue(any('duplicate' in e for e in structure_errors(config)))

    def test_starter_never_manufactures_approval(self):
        config=starter_config(threshold_cm=20)
        self.assertEqual(config['flood_threshold_m'],.2)
        self.assertFalse(config['policy']['profile_reviewed'])
        self.assertEqual(config['evidence'],[])
        self.assertIsNone(config['vertical_datum'])


@unittest.skipUnless(importlib.util.find_spec('qgis'), 'Use QGIS Python')
class WorkflowUXTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from qgis.core import QgsApplication
        cls.app=QgsApplication.instance() or QgsApplication([],False); cls.app.initQgis()
        cls.tmp=tempfile.TemporaryDirectory(prefix='nbs-ux-');cls.root=Path(cls.tmp.name)
        from stage1.demo import create_demo
        cls.source=create_demo(cls.root/'demo')
        cls.data=json.loads(cls.source.read_text())

    @classmethod
    def tearDownClass(cls):
        from qgis.core import QgsProject
        QgsProject.instance().clear();cls.tmp.cleanup()

    def config(self,name):
        data=json.loads(json.dumps(self.data));data.update(designs=['green_roof'],combinations=[],output_dir=name)
        path=self.source.parent/(name+'.json');path.write_text(json.dumps(data));return path

    def test_preflight_collects_missing_files_without_writing(self):
        from stage1.preflight import inspect_config
        source=self.config('missing')
        config=json.loads(source.read_text());config['flood']['path']='missing.tif';config['study_area']['path']='missing.gpkg';source.write_text(json.dumps(config))
        checked=inspect_config(source)
        self.assertFalse(checked.ok)
        self.assertGreaterEqual(sum(i['level']=='ERROR' for i in checked.issues),2)
        self.assertFalse((source.parent/'missing').exists())

    def test_preflight_checks_missing_fields_and_accumulates_errors(self):
        from stage1.preflight import inspect_config
        source=self.config('fields')
        config=json.loads(source.read_text());config['evidence'][0]['fields']={'land_type':'ABSENT'};config['ownership']['class_field']='ALSO_ABSENT';source.write_text(json.dumps(config))
        checked=inspect_config(source)
        self.assertEqual(sum(i['level']=='ERROR' for i in checked.issues),2)

    def test_preflight_reports_size_and_unit_conversion(self):
        from stage1.preflight import inspect_config
        checked=inspect_config(self.config('ready'))
        self.assertTrue(checked.ok,checked.text())
        self.assertEqual(checked.facts['Maximum cells in study bounding box'],120)

    def test_cancellation_during_rules_leaves_no_final_or_staging_output(self):
        from stage1.gis import run
        from stage1.runtime import RunCancelled
        source=self.config('cancel_rules');cancel=[False]
        def progress(percent,message):
            if percent>=28: cancel[0]=True
        with self.assertRaises(RunCancelled):run(source,False,progress=progress,cancelled=lambda:cancel[0])
        self.assertFalse((source.parent/'cancel_rules').exists())
        self.assertEqual(list(source.parent.glob('.cancel_rules_running_*')),[])

    def test_cancellation_after_database_write_cleans_staging(self):
        from stage1.gis import run
        from stage1.runtime import RunCancelled
        source=self.config('cancel_written');cancel=[False]
        def progress(percent,message):
            if percent>=72: cancel[0]=True
        with self.assertRaises(RunCancelled):run(source,False,progress=progress,cancelled=lambda:cancel[0])
        self.assertFalse((source.parent/'cancel_written').exists())
        self.assertEqual(list(source.parent.glob('.cancel_written_running_*')),[])

    def test_write_failure_does_not_publish_partial_results(self):
        from stage1.gis import run
        source=self.config('broken_write')
        with patch('stage1.gis.write_layer',side_effect=RuntimeError('Disk write failed')):
            with self.assertRaisesRegex(RuntimeError,'Disk write failed'):run(source,False)
        self.assertFalse((source.parent/'broken_write').exists())
        self.assertEqual(list(source.parent.glob('.broken_write_running_*')),[])

    def test_progress_timings_tasks_and_portable_project(self):
        from stage1.gis import run
        from qgis.core import QgsProject
        values=[];out=run(self.config('complete'),False,progress=lambda p,m:values.append(p))
        self.assertEqual(values,sorted(values));self.assertEqual(values[-1],100)
        self.assertGreater(json.loads((out/'performance.json').read_text())['total_seconds'],0)
        self.assertTrue((out/'evidence_tasks.csv').exists())
        self.assertIn('Find a map',(out/'report.html').read_text())
        project=QgsProject();self.assertTrue(project.read(str(out/'stage1.qgz')))
        self.assertTrue(all(l.isValid() for l in project.mapLayers().values()))
        self.assertTrue(all('_running_' not in l.source() for l in project.mapLayers().values()))
        with sqlite3.connect(out/'stage1.gpkg') as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        db.close()

    def test_overlay_cache_keeps_field_specific_coverage(self):
        from stage1.gis import indexed,join_evidence
        from qgis.core import QgsGeometry,QgsRectangle
        box=lambda x,w:QgsGeometry.fromRect(QgsRectangle(x,0,x+w,10))
        idx,records=indexed([(box(0,5),{'a':True,'b':True,'c':'I'}),(box(5,5),{'a':True,'b':None,'c':'OUTSIDE'})])
        result=join_evidence(box(0,10),idx,records,{'all':'a','partial':'b','protection_zone':'c'})
        self.assertEqual(result,{'all':True,'partial':None,'protection_zone':'I'})

    def test_spatial_lookup_matches_brute_force_for_nonconvex_shapes(self):
        from stage1.muriel import SpatialLookup
        from qgis.core import QgsGeometry,QgsRectangle
        box=lambda x,y,w,h:QgsGeometry.fromRect(QgsRectangle(x,y,x+w,y+h))
        ring=box(0,0,100,100).difference(box(2,2,96,96))
        records=[(ring,{'id':'ring'}),(box(48,48,1,1),{'id':'inside'}),(box(200,0,1,1),{'id':'distant'})]
        lookup=SpatialLookup(records); query=box(50,50,1,1)
        self.assertAlmostEqual(lookup.minimum(query),min(query.distance(g) for g,_ in records))
        self.assertEqual(lookup.within(query,2),[records[1][1]])
        self.assertIsNone(SpatialLookup([]).minimum(query))

    def test_gui_builds_config_from_saved_layers_without_approvals(self):
        from qgis.core import QgsProject,QgsRasterLayer,QgsVectorLayer
        from stage1.gui import StageOneDialog
        dialog=StageOneDialog();dialog.folder.setText(str(self.root/'gui_workspace'))
        raster=QgsRasterLayer(str(self.source.parent/'inputs/flood_cm.tif'),'test flood')
        boundary=QgsVectorLayer(str(self.source.parent/'inputs/synthetic.gpkg')+'|layername=study_area','boundary','ogr')
        for layer in (raster,boundary):QgsProject.instance().addMapLayer(layer)
        dialog.flood.combo.setLayer(raster);dialog.boundary.combo.setLayer(boundary);dialog.threshold.setValue(20)
        config=dialog.configuration()
        self.assertEqual(config['flood']['units'],'cm');self.assertEqual(config['flood_threshold_m'],.2)
        self.assertEqual(config['study_area']['layer'],'study_area')
        self.assertFalse(config['policy']['profile_reviewed'])
        checked=dialog.check_inputs()[1];self.assertTrue(checked.ok,checked.text())
        self.assertTrue(any(i['level']=='WARNING' for i in checked.issues))
        dialog.close()
        for layer in (raster,boundary):QgsProject.instance().removeMapLayer(layer.id())

    def test_gui_registered_configuration_is_not_rewritten(self):
        from stage1.gui import StageOneDialog
        dialog=StageOneDialog();source=self.config('registered');before=source.read_bytes()
        dialog.use_configuration(source);self.assertEqual(dialog.configuration(),source)
        dialog.check_inputs();self.assertEqual(source.read_bytes(),before);self.assertFalse(dialog.input_page.isEnabled())
        dialog.close()

    def test_cli_invalid_config_returns_actionable_error_without_traceback(self):
        import subprocess
        source=self.root/'bad.json';source.write_text('{bad json')
        result=subprocess.run(['/usr/bin/python3','-m','stage1','validate',str(source),'--json'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        checked=json.loads(result.stdout);self.assertFalse(checked['ok']);self.assertIn('line 1',checked['issues'][0]['message'])
        self.assertNotIn('Traceback',result.stderr)

    def test_csv_optimisation_preserves_standard_export_including_missing_values(self):
        import csv
        from stage1.gis import csv_write
        cases=[[{'a':'Reason, with comma','b':'Two\nlines'},{'a':None,'b':True}],
               [{'a':1},{'b':'Köln'}],[{'one':'Only column'}]]
        for i,rows in enumerate(cases):
            actual=self.root/f'actual_{i}.csv';expected=self.root/f'expected_{i}.csv'
            csv_write(actual,rows)
            with expected.open('w',newline='',encoding='utf-8') as file:
                writer=csv.DictWriter(file,fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
                writer.writeheader();writer.writerows(rows)
            self.assertEqual(actual.read_bytes(),expected.read_bytes())

    def test_gui_threshold_copy_preserves_expert_inputs_and_original(self):
        from stage1.gui import StageOneDialog
        from stage1.configuration import resolve_config
        dialog=StageOneDialog();source=self.config('threshold_original');before=source.read_bytes()
        dialog.use_configuration(source);copy=dialog.clone_for_run(self.root/'threshold_runs',20)
        config=resolve_config(copy);original=resolve_config(source)
        self.assertEqual(source.read_bytes(),before)
        self.assertEqual(config['flood_threshold_m'],.2)
        self.assertNotEqual(config['output_dir'],original['output_dir'])
        for field in ('flood','study_area','evidence','policy','ownership','designs'):
            self.assertEqual(config[field],original[field])
        dialog.close()
