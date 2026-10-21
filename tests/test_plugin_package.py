"""Verify the exact ZIP users install, including a complete bundled-engine run."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile


@unittest.skipUnless(importlib.util.find_spec('qgis'),'Use QGIS Python')
class PluginPackageTests(unittest.TestCase):
    def test_installable_package_runs_without_repository_imports(self):
        from qgis.core import QgsApplication,QgsProject,QgsVectorLayer
        from qgis.PyQt.QtWidgets import QWidget
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        app=QgsApplication.instance() or QgsApplication([],False);app.initQgis()
        root=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('build_qgis_plugin',root/'scripts/build_qgis_plugin.py')
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory(prefix='nbs-plugin-test-') as tmp:
            tmp=Path(tmp); archive_path=builder.build(tmp/'plugin.zip')
            with ZipFile(archive_path) as archive:
                self.assertIsNone(archive.testzip());archive.extractall(tmp/'installed')
                self.assertIn('nbs_stage1/metadata.txt',archive.namelist())
                for path in (root/'stage1').glob('*.py'):
                    self.assertEqual(archive.read('nbs_stage1/stage1/'+path.name),path.read_bytes())
            sys.path.insert(0,str(tmp/'installed'))
            class FakeInterface:
                def __init__(self):self.window=QWidget();self.actions=[]
                def mainWindow(self):return self.window
                def addPluginToMenu(self,menu,action):self.actions.append(action)
                def addToolBarIcon(self,action):pass
                def removePluginMenu(self,menu,action):self.actions.remove(action)
                def removeToolBarIcon(self,action):pass
            try:
                import nbs_stage1
                iface=FakeInterface();plugin=nbs_stage1.classFactory(iface);plugin.initGui();plugin.open()
                self.assertTrue(plugin.dialog.isVisible())
                from nbs_stage1.stage1.demo import create_demo
                source=create_demo(tmp/'bundled-demo')
                config=json.loads(source.read_text());config.update(designs=['green_roof'],combinations=[],preparation={'enabled':True});source.write_text(json.dumps(config))
                sentinel=QgsVectorLayer('Polygon?crs=EPSG:25832','unsaved project','memory');QgsProject.instance().addMapLayer(sentinel);sid=sentinel.id()
                plugin.dialog.use_configuration(source);plugin.dialog.export_maps.setChecked(False)
                plugin.dialog.start_run();app.processEvents()
                self.assertFalse(plugin.dialog.running)
                self.assertTrue((tmp/'bundled-demo/results/stage1.qgz').exists())
                self.assertTrue(plugin.dialog.report_button.isEnabled())
                self.assertIsNotNone(QgsProject.instance().mapLayer(sid))
                from nbs_stage1.stage1.demo import create_area_demo
                planning_source=create_area_demo(tmp/'bundled-planning',crs='EPSG:32734')
                plugin.dialog.use_configuration(planning_source)
                self.assertEqual(plugin.dialog.mode.currentData(),'planning')
                plugin.dialog.start_run();app.processEvents()
                self.assertFalse(plugin.dialog.running)
                self.assertTrue((tmp/'bundled-planning/results/planning_shortlist.csv').is_file())
                self.assertIsNotNone(QgsProject.instance().mapLayer(sid))
                QgsProject.instance().removeMapLayer(sid)
                plugin.unload();self.assertEqual(iface.actions,[])
            finally:
                sys.path.remove(str(tmp/'installed'))
                for name in list(sys.modules):
                    if name=='nbs_stage1' or name.startswith('nbs_stage1.'):del sys.modules[name]
