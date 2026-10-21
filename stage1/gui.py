"""Native QGIS guided setup. No web server, account or JSON editing required."""
from datetime import datetime
from copy import deepcopy
import html
import json
from pathlib import Path
import re
from uuid import uuid4

from qgis.PyQt.QtCore import QTimer, QUrl, Qt
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QProgressBar, QPushButton, QScrollArea, QSpinBox, QTabWidget, QTextBrowser, QDialogButtonBox,
    QVBoxLayout, QWidget, QInputDialog,
)
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsProject, QgsProviderRegistry, QgsRasterLayer, QgsVectorLayer
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox, QgsProjectionSelectionWidget

from .catalogue import DESIGNS
from .configuration import resolve_config, starter_config
from .preflight import inspect_config
from .runtime import RunCancelled
from .profiles import profile_template, validate_policy
from .engine import MURIEL_DEFAULTS


def file_spec(layer):
    if layer is None:
        return None
    if isinstance(layer, QgsVectorLayer) and layer.subsetString():
        raise ValueError(f'Export the filtered layer "{layer.name()}" to a saved GeoPackage first, so its selected extent and records are preserved.')
    decoded = QgsProviderRegistry.instance().decodeUri(layer.providerType(), layer.source())
    path = decoded.get('path')
    if not path or not Path(path).is_file():
        raise ValueError(f'Save "{layer.name()}" to a local GeoPackage or GeoTIFF first; temporary layers and web images cannot supply reusable numeric inputs.')
    spec = {'path': str(Path(path).resolve()), 'metadata': {'provider': '', 'date': '', 'version': '', 'license': ''}}
    name = decoded.get('layerName') or decoded.get('layername')
    if name:
        spec['layer'] = name
    return spec


class LayerPicker(QWidget):
    def __init__(self, raster=False):
        super().__init__()
        layout = QHBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        self.combo = QgsMapLayerComboBox()
        self.combo.setFilters(Qgis.LayerFilters(Qgis.LayerFilter.PolygonLayer | Qgis.LayerFilter.RasterLayer if raster else Qgis.LayerFilter.PolygonLayer))
        self.combo.setAllowEmptyLayer(True, 'Choose a layer…')
        self.combo.setLayer(None)
        layout.addWidget(self.combo, 1)
        add = QPushButton('Add file…'); add.setMaximumWidth(90); add.clicked.connect(self.add_file); layout.addWidget(add)
        self.metadata = {'provider': '', 'date': '', 'version': '', 'license': ''}
        details = QPushButton('Source…'); details.setMaximumWidth(80); details.clicked.connect(self.edit_metadata); layout.addWidget(details)
        self.combo.layerChanged.connect(lambda _: self.metadata.update({k: '' for k in self.metadata}))

    def edit_metadata(self):
        dialog=QDialog(self); dialog.setWindowTitle('Input source details'); form=QFormLayout(dialog)
        fields={}
        for key,label in [('provider','Provider / organisation'),('date','Source date'),('version','Version / release'),('license','Licence / access conditions')]:
            fields[key]=QLineEdit(self.metadata[key]); form.addRow(label,fields[key])
        buttons=QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec_()==QDialog.Accepted:
            self.metadata={key:widget.text().strip() for key,widget in fields.items()}

    def add_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Add a saved GIS input', '', 'GIS data (*.gpkg *.tif *.tiff *.shp *.geojson);;All files (*)')
        if not path:
            return
        try:
            if Path(path).suffix.lower() in ('.tif','.tiff'):
                layer = QgsRasterLayer(path, Path(path).stem)
            else:
                details = QgsProviderRegistry.instance().querySublayers(path)
                if len(details) > 1:
                    name, ok = QInputDialog.getItem(self, 'Choose a layer', 'Layer in this file', [d.name() for d in details], 0, False)
                    if not ok:
                        return
                    uri = next(d.uri() for d in details if d.name() == name)
                else:
                    uri = details[0].uri() if details else path
                layer = QgsVectorLayer(uri, Path(path).stem, 'ogr')
            if not layer.isValid():
                raise ValueError('The selected layer could not be opened.')
            QgsProject.instance().addMapLayer(layer)
            self.combo.setLayer(layer)
        except Exception as exc:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.warning(self, 'Cannot add input', str(exc))

    def spec(self):
        spec=file_spec(self.combo.currentLayer())
        if spec: spec['metadata']=dict(self.metadata)
        return spec


class StageOneDialog(QDialog):
    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.loaded_path = None
        self.output = None
        self.running = False
        self.cancelled = False
        self.token = self.new_token()
        self.setWindowTitle('NbS Stage 1 · opportunity mapping')
        self.resize(1040, 790)
        outer = QVBoxLayout(self)
        title = QLabel('<h2>NbS opportunity mapping</h2>Choose inputs → check readiness → create your QGIS results.')
        outer.addWidget(title)
        registered = QHBoxLayout()
        self.configuration_label = QLabel('Guided setup · no configuration editing needed')
        registered.addWidget(self.configuration_label, 1)
        self.open_config = QPushButton('Open registered configuration…'); self.open_config.clicked.connect(self.choose_configuration)
        self.new_button = QPushButton('New guided setup'); self.new_button.clicked.connect(self.reset_configuration)
        registered.addWidget(self.open_config); registered.addWidget(self.new_button); outer.addLayout(registered)
        self.tabs = QTabWidget(); outer.addWidget(self.tabs, 1)
        self.input_form, self.input_page = self.page('1 · Inputs')
        self.area = QLineEdit(); self.area.setPlaceholderText('Name of your study area'); self.name = QLineEdit('STUDY_RUN')
        self.scenario = QLineEdit(); self.scenario.setPlaceholderText('Actual event identifier from the flood provider')
        self.period = QSpinBox(); self.period.setRange(0,100000); self.period.setValue(0); self.period.setSpecialValueText('Unconfirmed')
        self.units = QComboBox(); self.units.addItem('Choose depth units…',None); self.units.addItem('Centimetres (cm)', 'cm'); self.units.addItem('Metres (m)', 'm')
        self.threshold = QDoubleSpinBox(); self.threshold.setRange(0,100000); self.threshold.setDecimals(2); self.threshold.setValue(10); self.threshold.setSuffix(' cm')
        for label, widget in [('Study area name',self.area),('Run name',self.name),('Flood scenario',self.scenario),('Stated return period (years)',self.period),('Flood depth units',self.units),('Intervention threshold',self.threshold)]:
            self.input_form.addRow(label, widget)
        self.processing_crs = QgsProjectionSelectionWidget()
        self.processing_crs.setOptionVisible(QgsProjectionSelectionWidget.CrsNotSet,True)
        self.processing_crs.setNotSetText('Choose a local projected CRS…')
        self.processing_crs.setCrs(QgsCoordinateReferenceSystem())
        self.input_form.addRow('Processing CRS · projected metres', self.processing_crs)
        self.jurisdiction = QLineEdit(); self.jurisdiction.setPlaceholderText('Governing city / region / country; optional for generic planning')
        self.input_form.addRow('Rule jurisdiction',self.jurisdiction)
        self.selected_policy = profile_template()
        policy_row = QWidget(); policy_layout = QHBoxLayout(policy_row); policy_layout.setContentsMargins(0,0,0,0)
        self.policy_combo = QComboBox(); self.policy_combo.addItem('Generic · local rules unconfigured','generic'); self.policy_combo.addItem('Köln · thesis reference profile','koeln')
        self.policy_combo.currentIndexChanged.connect(self.select_policy)
        self.load_policy_button = QPushButton('Load local profile…'); self.load_policy_button.clicked.connect(self.load_local_policy)
        policy_layout.addWidget(self.policy_combo,1); policy_layout.addWidget(self.load_policy_button)
        self.input_form.addRow('Local rules',policy_row)
        self.flood = LayerPicker(raster=True); self.boundary = LayerPicker()
        self.boundary.combo.layerChanged.connect(self.suggest_crs)
        self.input_form.addRow('Flood depth layer · required',self.flood)
        self.depth_field = QgsFieldComboBox(); self.id_field = QgsFieldComboBox()
        self.band=QSpinBox(); self.band.setRange(1,1)
        self.flood.combo.layerChanged.connect(self.flood_changed)
        self.input_form.addRow('Vector flood: depth field',self.depth_field); self.input_form.addRow('Vector flood: unique ID field',self.id_field)
        self.input_form.addRow('Raster flood: depth band',self.band)
        self.flood_changed(None)
        self.input_form.addRow('Study boundary · required', self.boundary)
        folder = QWidget(); folder_layout = QHBoxLayout(folder); folder_layout.setContentsMargins(0,0,0,0)
        self.folder = QLineEdit(); self.folder.setPlaceholderText('Choose where to save configurations and new result folders')
        browse = QPushButton('Browse…'); browse.clicked.connect(self.choose_folder)
        folder_layout.addWidget(self.folder); folder_layout.addWidget(browse)
        self.input_form.addRow('Workspace folder · required',folder)
        self.auto_prepare=QCheckBox('Automatically reproject, clip and align inputs to the native flood grid')
        self.auto_prepare.setChecked(True);self.input_form.addRow(self.auto_prepare)
        self.input_form.addRow(self.note('Choose a projected CRS in metres appropriate to this area. A declared input CRS can populate the selection; unknown CRSs are never guessed. Local rules and event definitions do not transfer automatically. The 10 cm threshold is a configurable project assumption.'))
        self.designs = QListWidget(); self.designs.setMinimumHeight(145)
        for design, values in DESIGNS.items():
            item = QListWidgetItem(values[0]); item.setData(Qt.UserRole,design); item.setFlags(item.flags() | Qt.ItemIsUserCheckable); item.setCheckState(Qt.Checked); self.designs.addItem(item)
        self.input_form.addRow('NbS designs to assess',self.designs)
        self.evidence_form, self.evidence_page = self.page('2 · Evidence && MURIEL')
        self.evidence_form.addRow(self.note('Optional inputs improve completeness. Missing evidence stays conditional. Layer names and field names must follow the input specification; registered configurations support additional layers, raster evidence and combinations.'))
        self.site_evidence = LayerPicker(); self.evidence_join = QComboBox(); self.evidence_join.addItems(['Spatial overlay','Join by unit_id'])
        self.evidence_form.addRow('Prepared site/groundwater evidence', self.site_evidence)
        self.evidence_form.addRow('Evidence join method', self.evidence_join)
        self.gw_state = QLineEdit('UNKNOWN_DESIGN_GROUNDWATER'); self.datum = QLineEdit(); self.datum.setPlaceholderText('Documented common height datum / reference')
        self.evidence_form.addRow('Design groundwater scenario',self.gw_state); self.evidence_form.addRow('Common vertical datum',self.datum)
        self.profile_reviewed=QCheckBox('Local rule profile checked against current primary sources and authority requirements')
        self.profile_reference=QLineEdit(); self.profile_reference.setPlaceholderText('Dated local review reference; required if checked')
        self.evidence_form.addRow(self.profile_reviewed); self.evidence_form.addRow('Local rule review reference',self.profile_reference)
        self.owners = LayerPicker(); self.owner_field = QgsFieldComboBox()
        self.owners.combo.layerChanged.connect(self.owner_field.setLayer)
        self.evidence_form.addRow('Ownership polygons',self.owners); self.evidence_form.addRow('Ownership category field',self.owner_field)
        self.owner_values = {}
        for key,label,default in [('municipal','Municipal values','CITY'),('private','Private values','PRIVATE'),('other_public','Other public values','OTHER_PUBLIC'),('unknown','Unknown values','UNKNOWN')]:
            widget=QLineEdit(default); widget.setPlaceholderText('Exact values, separated with ;'); self.owner_values[key]=widget; self.evidence_form.addRow(label,widget)
        self.muriel_enabled=QCheckBox('Include MURIEL public-space screening'); self.muriel_enabled.setChecked(False); self.evidence_form.addRow(self.muriel_enabled)
        self.muriel_criteria = {}
        for key,label in [('min_area_m2','Minimum flood area (m²)'),('min_max_depth_m','Depth criterion (m)'),('receptor_distance_m','Receptor distance (m)'),('municipal_distance_m','Municipal land distance (m)'),('destination_distance_m','Destination search distance (m)'),('protect_overlap_fraction','Protect-retention overlap (0–1)')]:
            field=QDoubleSpinBox(); field.setRange(0,1 if key=='protect_overlap_fraction' else 1000000); field.setDecimals(3); field.setValue(MURIEL_DEFAULTS[key])
            self.muriel_criteria[key]=field; self.evidence_form.addRow('MURIEL · '+label,field)
        self.muriel_footprint=QComboBox(); self.muriel_footprint.addItems(['depth_mask','inundation_maximum']); self.evidence_form.addRow('MURIEL footprint interpretation',self.muriel_footprint)
        self.muriel_reference=QLineEdit(); self.muriel_reference.setPlaceholderText('Dated project adoption / planning criteria reference for this jurisdiction')
        self.evidence_form.addRow('MURIEL local adoption reference',self.muriel_reference)
        self.owner_verified=QCheckBox('Municipal ownership has been verified'); self.evidence_form.addRow(self.owner_verified)
        self.inventory = {}
        for key,label in [('land','Ownership coverage'),('receptors','Buildings and sensitive-object footprints'),('roads','Road footprint polygons'),('usable_space','Assessed multifunctional destination spaces')]:
            picker = None if key=='land' else LayerPicker()
            if picker:
                self.evidence_form.addRow(label,picker)
            covered=QCheckBox('Complete inventory through the search extension'); ref=QLineEdit(); ref.setPlaceholderText('Dated source / assessment reference')
            self.evidence_form.addRow(label+' · evidence',ref); self.evidence_form.addRow(covered)
            self.inventory[key]=(picker,covered,ref)
        self.destination_id=QgsFieldComboBox(); self.usable_field=QgsFieldComboBox()
        self.inventory['usable_space'][0].combo.layerChanged.connect(self.destination_id.setLayer)
        self.inventory['usable_space'][0].combo.layerChanged.connect(self.usable_field.setLayer)
        self.evidence_form.addRow('Destination unique ID field', self.destination_id); self.evidence_form.addRow('Usable field (true/false/NULL)', self.usable_field)
        self.evidence_form.addRow(self.note('The displayed MURIEL values are the Porz/Eil reference example, not universal rules. Register locally appropriate values and a dated adoption reference. Coverage and verification boxes are evidence declarations. Proximity does not prove routing.'))
        results=QWidget(); layout=QVBoxLayout(results); self.tabs.addTab(results,'3 · Run && results')
        self.export_maps=QCheckBox('Print PNG maps and PDF atlases'); self.export_maps.setChecked(True); layout.addWidget(self.export_maps)
        self.duplicate_button=QPushButton('Copy registered configuration for a new threshold run…'); self.duplicate_button.setEnabled(False)
        self.duplicate_button.clicked.connect(self.duplicate_configuration); layout.addWidget(self.duplicate_button)
        layout.addWidget(self.note('For a faster first run, turn printing off. The QGIS project, all decisions and source references are still produced.'))
        self.messages=QTextBrowser(); self.messages.setOpenExternalLinks(True); layout.addWidget(self.messages,1)
        self.messages.setText('Choose your flood event, units, study boundary and processing CRS, then check inputs. Generic local rules stay conditional. You can load a registered local profile or an existing configuration.')
        buttons=QHBoxLayout()
        self.report_button=QPushButton('Open report'); self.report_button.setEnabled(False); self.report_button.clicked.connect(lambda: self.open_result('report.html'))
        self.folder_button=QPushButton('Open results folder'); self.folder_button.setEnabled(False); self.folder_button.clicked.connect(lambda: self.open_result(''))
        buttons.addWidget(self.report_button); buttons.addWidget(self.folder_button); buttons.addStretch(); layout.addLayout(buttons)
        self.progress=QProgressBar(); self.progress.setRange(0,100); outer.addWidget(self.progress)
        self.status=QLabel('Ready for input selection'); outer.addWidget(self.status)
        actions=QHBoxLayout(); self.check_button=QPushButton('Check inputs'); self.check_button.clicked.connect(self.check_inputs)
        self.prepare_button=QPushButton('Prepare GIS data…');self.prepare_button.clicked.connect(self.prepare_inputs);actions.addWidget(self.prepare_button)
        self.run_button=QPushButton('Run Stage 1'); self.run_button.clicked.connect(self.start_run)
        self.cancel_button=QPushButton('Cancel run'); self.cancel_button.setEnabled(False); self.cancel_button.clicked.connect(self.request_cancel)
        actions.addWidget(self.check_button); actions.addWidget(self.run_button); actions.addWidget(self.cancel_button); outer.addLayout(actions)

    @staticmethod
    def new_token():
        return datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid4().hex[:6]

    def prepare_inputs(self):
        from .preparation_gui import PreparationDialog
        PreparationDialog(self).exec_()

    @staticmethod
    def note(text):
        label=QLabel(text); label.setWordWrap(True); label.setStyleSheet('color:#49616b; padding:5px;'); return label

    def page(self,name):
        widget=QWidget(); form=QFormLayout(widget); form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(widget); self.tabs.addTab(scroll,name)
        return form, widget

    def choose_folder(self):
        path=QFileDialog.getExistingDirectory(self,'Choose a workspace folder')
        if path: self.folder.setText(path)

    def suggest_crs(self,layer):
        if layer and not self.processing_crs.crs().isValid():
            crs=layer.crs()
            if crs.isValid() and not crs.isGeographic() and crs.mapUnits()==Qgis.DistanceUnit.Meters:
                self.processing_crs.setCrs(crs)

    def select_policy(self):
        kind=self.policy_combo.currentData()
        if kind in ('generic','koeln'):
            self.selected_policy=profile_template(kind)
            if kind=='koeln' and not self.jurisdiction.text().strip():self.jurisdiction.setText('Koeln')
            self.profile_reviewed.setChecked(False); self.profile_reference.clear()

    def load_local_policy(self):
        path,_=QFileDialog.getOpenFileName(self,'Load a registered local rule profile','','JSON (*.json)')
        if not path:return
        try:
            data=json.loads(Path(path).read_text(encoding='utf-8-sig')); policy=validate_policy(data.get('policy',data))
            self.selected_policy=policy
            self.policy_combo.addItem('Local · '+policy['profile_id'],'custom');self.policy_combo.setCurrentIndex(self.policy_combo.count()-1)
            if not self.jurisdiction.text().strip():self.jurisdiction.setText(policy['municipality'])
            self.profile_reviewed.setChecked(policy['profile_reviewed']);self.profile_reference.setText(policy['profile_review_ref'] or '')
        except Exception as exc:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.warning(self,'Cannot load local profile',str(exc))

    def flood_changed(self, layer):
        self.suggest_crs(layer)
        vector=isinstance(layer,QgsVectorLayer)
        for widget in (self.depth_field,self.id_field):
            widget.setEnabled(vector); widget.setLayer(layer if vector else None)
        self.band.setEnabled(isinstance(layer,QgsRasterLayer))
        self.band.setMaximum(layer.bandCount() if isinstance(layer,QgsRasterLayer) else 1)

    def choose_configuration(self):
        path,_=QFileDialog.getOpenFileName(self,'Open a registered configuration','','JSON (*.json)')
        if path: self.use_configuration(path)

    def use_configuration(self,path):
        self.loaded_path=Path(path).resolve(); self.configuration_label.setText('Registered: '+str(self.loaded_path))
        self.input_page.setEnabled(False); self.evidence_page.setEnabled(False)
        self.duplicate_button.setEnabled(True)

    def reset_configuration(self):
        self.loaded_path=None; self.configuration_label.setText('Guided setup · no configuration editing needed')
        self.input_page.setEnabled(True); self.evidence_page.setEnabled(True)
        self.duplicate_button.setEnabled(False)

    def clone_for_run(self,workspace,threshold_cm):
        config=resolve_config(self.loaded_path)
        token=self.new_token();slug=re.sub(r'[^A-Za-z0-9_-]+','_',config['run_id'])+'_'+token
        workspace=Path(workspace).resolve();config['run_id']=slug
        config['output_dir']=str(workspace/'runs'/slug);config['flood_threshold_m']=float(threshold_cm)/100
        target=workspace/'configurations'/(slug+'.json');target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('x',encoding='utf-8') as file:json.dump(config,file,indent=2,ensure_ascii=False)
        self.use_configuration(target)
        return target

    def duplicate_configuration(self):
        try:
            config=resolve_config(self.loaded_path)
            threshold,ok=QInputDialog.getDouble(self,'New threshold run','Intervention threshold (cm)',config['flood_threshold_m']*100,0,100000,2)
            if not ok:return
            folder=QFileDialog.getExistingDirectory(self,'Workspace for the new run')
            if not folder:return
            self.clone_for_run(folder,threshold);self.check_inputs()
        except Exception as exc:self.messages.setPlainText(str(exc))

    def configuration(self):
        if self.loaded_path: return self.loaded_path
        if not self.folder.text().strip():
            raise ValueError('Choose a workspace folder for configurations and results.')
        slug=re.sub(r'[^A-Za-z0-9_-]+','_',self.name.text().strip()).strip('_')
        if not slug:
            raise ValueError('Enter a run name.')
        flood=self.flood.spec()
        if flood:
            flood.update(type='vector' if isinstance(self.flood.combo.currentLayer(),QgsVectorLayer) else 'raster',units=self.units.currentData())
            if flood['type']=='vector':
                flood.update(depth_field=self.depth_field.currentField(),id_field=self.id_field.currentField())
            else: flood['band']=self.band.value()
        workspace=Path(self.folder.text()).expanduser().resolve()
        config=starter_config(flood=flood,study_area=self.boundary.spec(),output_dir=workspace/'runs'/(slug+'_'+self.token),area_label=self.area.text().strip(),scenario=self.scenario.text().strip(),threshold_cm=self.threshold.value())
        config['crs']=self.processing_crs.crs().authid() or self.processing_crs.crs().toWkt()
        config['jurisdiction']=self.jurisdiction.text().strip()
        config['policy']=deepcopy(self.selected_policy); config['policy']['municipality']=config['jurisdiction']
        config['run_id']=slug+'_'+self.token
        config['preparation']={'enabled':self.auto_prepare.isChecked()}
        config['stated_return_period_years']=self.period.value() or None
        config['return_period_source']='User-entered event metadata; provider verification outstanding.' if self.period.value() else None
        config['policy'].update(profile_reviewed=self.profile_reviewed.isChecked(),profile_review_ref=self.profile_reference.text().strip() or None)
        if self.profile_reviewed.isChecked() and not config['policy']['profile_review_ref']:
            raise ValueError('Enter the dated local rule review reference, or leave the review unconfirmed.')
        if getattr(self, 'mode', None) is not None and self.mode.currentData() == 'planning':
            return config
        config['groundwater_scenario_id']=self.gw_state.text().strip()
        config['vertical_datum']=self.datum.text().strip() or None
        config['designs']=[self.designs.item(i).data(Qt.UserRole) for i in range(self.designs.count()) if self.designs.item(i).checkState()==Qt.Checked]
        evidence=self.site_evidence.spec()
        if evidence:
            evidence.update(join='spatial' if self.evidence_join.currentIndex()==0 else 'id',id_field='unit_id')
            config['evidence']=[evidence]
        owner=self.owners.spec()
        if owner:
            mapping={}
            for category,widget in self.owner_values.items():
                for value in (v.strip() for v in widget.text().split(';') if v.strip()):
                    if value in mapping and mapping[value]!=category:
                        raise ValueError(f'Ownership value "{value}" is assigned to more than one category.')
                    mapping[value]=category
            owner.update(class_field=self.owner_field.currentField(),mapping=mapping)
            config['ownership']=owner
        m=config['muriel']; m['enabled']=self.muriel_enabled.isChecked()
        if m['enabled']:
            m.update(thresholds={key:field.value() for key,field in self.muriel_criteria.items()},
                     criteria_profile_id='project_muriel_v1',criteria_scope=config['jurisdiction'],criteria_adoption_ref=self.muriel_reference.text().strip() or None)
            m['thresholds']['footprint_mode']=self.muriel_footprint.currentText()
            if m['criteria_adoption_ref']:
                m['criteria_source']={'citation':'Project-registered MURIEL criteria: '+m['criteria_adoption_ref'],
                                      'locator':'Run configuration muriel.thresholds; adapted from Schwerdorf (2022)', 'url':'', 'status':'project_registered_planning_criteria'}
            if owner:
                _,covered,ref=self.inventory['land']
                m['municipal_land']={**owner,'municipal_values':[v for v,c in owner['mapping'].items() if c=='municipal'],
                                     'municipal_verified':self.owner_verified.isChecked(),'coverage_complete':covered.isChecked(),'evidence_ref':ref.text().strip() or None}
            for key in ('receptors','roads','usable_space'):
                picker,covered,ref=self.inventory[key]; spec=picker.spec()
                if spec:
                    spec.update(coverage_complete=covered.isChecked(),evidence_ref=ref.text().strip() or None)
                    if key=='usable_space':
                        spec.update(id_field=self.destination_id.currentField(),usable_field=self.usable_field.currentField())
                    m[key]=[spec] if key=='receptors' else spec
        return config

    def check_inputs(self):
        self.tabs.setCurrentIndex(2)
        try:
            source=self.configuration()
            checked=inspect_config(source)
            rows=''.join('<tr><td>'+html.escape(i['level'])+'</td><td>'+html.escape(i['input'])+'</td><td>'+html.escape(i['message'])+'<br><small>'+html.escape(i['action'])+'</small></td></tr>' for i in checked.issues)
            facts=''.join('<li>'+html.escape(str(k))+': '+html.escape(str(v))+'</li>' for k,v in checked.facts.items())
            self.messages.setHtml('<h3>'+('Ready for screening' if checked.ok else 'Inputs need attention')+'</h3><p>Warnings identify evidence gaps; a successful run does not resolve them.</p><table cellpadding="6">'+rows+'</table><ul>'+facts+'</ul>')
            self.status.setText('Checks passed; review warnings before interpreting results.' if checked.ok else 'Fix the listed errors and check again.')
            return (source,checked)
        except Exception as exc:
            self.messages.setPlainText(str(exc)); self.status.setText('Inputs need attention')
            return None,None

    def start_run(self):
        if self.running: return
        source,checked=self.check_inputs()
        if not checked or not checked.ok: return
        if isinstance(source,dict):
            config_dir=Path(self.folder.text()).expanduser().resolve()/'configurations'
            try:
                config_dir.mkdir(parents=True,exist_ok=True)
                config_path=config_dir/(source['run_id']+'.json')
                with config_path.open('x',encoding='utf-8') as file:
                    json.dump(source,file,indent=2,ensure_ascii=False)
                source=config_path
            except OSError as exc:
                self.messages.setPlainText(f'Cannot save the run configuration: {exc}'); return
        self.running=True; self.cancelled=False; self.progress.setValue(0)
        self.report_button.setEnabled(False); self.folder_button.setEnabled(False)
        for widget in (self.check_button,self.run_button,self.open_config,self.new_button,self.input_page,self.evidence_page,self.export_maps,self.duplicate_button,self.prepare_button): widget.setEnabled(False)
        self.cancel_button.setEnabled(True)
        QTimer.singleShot(0,lambda: self.execute_run(source))

    def execute_run(self,source):
        from .gis import run
        def progress(percent,message):
            self.progress.setValue(int(percent)); self.status.setText(message); QApplication.processEvents()
        def cancelled():
            QApplication.processEvents()
            return self.cancelled
        try:
            self.output=run(source,export_maps=self.export_maps.isChecked(),progress=progress,cancelled=cancelled)
            self.report_button.setEnabled(True); self.folder_button.setEnabled(True)
            self.messages.append('<h3>Results ready</h3><p>'+html.escape(str(self.output))+'</p><p>Open <b>stage1.qgz</b> in QGIS, choose a map theme, and use <b>Identify Features</b> for reasons and references. The report summarises outstanding evidence.</p>')
            self.status.setText('Completed · results and audit saved'); self.token=self.new_token()
        except RunCancelled as exc:
            self.messages.append(html.escape(str(exc))); self.status.setText('Cancelled · unfinished output removed')
            self.token=self.new_token()
        except Exception as exc:
            self.messages.append('<p>Run could not complete: '+html.escape(str(exc))+'</p>'); self.status.setText('Run failed · correct the input or evidence issue and retry')
            self.token=self.new_token()
        finally:
            self.running=False; self.cancel_button.setEnabled(False)
            for widget in (self.check_button,self.run_button,self.open_config,self.new_button,self.export_maps,self.prepare_button): widget.setEnabled(True)
            self.input_page.setEnabled(self.loaded_path is None); self.evidence_page.setEnabled(self.loaded_path is None)
            self.duplicate_button.setEnabled(self.loaded_path is not None)

    def request_cancel(self):
        self.cancelled=True; self.status.setText('Cancelling at the next safe checkpoint…')

    def reject(self):
        if self.running: self.request_cancel()
        else: super().reject()

    def open_result(self,name):
        if self.output: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output/name)))
