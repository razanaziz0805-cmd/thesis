"""A short default setup, with the detailed qualification panel available on demand."""
from qgis.PyQt.QtWidgets import QComboBox, QFormLayout, QGroupBox, QLineEdit, QVBoxLayout, QWidget
from qgis.gui import QgsFieldComboBox
from qgis.core import QgsRasterLayer, QgsVectorLayer

from .gui import LayerPicker, StageOneDialog


class PlanningDialog(StageOneDialog):
    def __init__(self, iface=None, parent=None):
        super().__init__(iface, parent)
        self.setWindowTitle('NbS planning · from flood map to next action')
        self.mode = QComboBox()
        self.mode.addItem('Planning opportunities · start with two layers', 'planning')
        self.mode.addItem('Advanced · detailed qualification and MURIEL', 'engineering')
        self.layout().insertWidget(1, self.mode)
        self.mode.currentIndexChanged.connect(self.change_mode)
        self.advanced_tab = self.tabs.widget(1)
        self.tabs.removeTab(1)
        self.planning_page = QWidget(); form = QFormLayout(self.planning_page)
        form.addRow(self.note('These sections are optional. Start with boundary and flood depth; add context and known restrictions when available. '
                              'No detailed engineering fields are needed to locate flood action areas. Map source categories explicitly; unmapped values stay unknown.'))
        self.planning_inputs = {}
        groups = [
            ('surfaces', 'Surface types · adds NbS investigation maps',
             [('roof','Roof'),('open_space','Open space'),('verge','Verge'),('pavement','Paved area'),('parking','Parking'),('footway','Footway')]),
            ('ownership', 'Ownership · adds municipal / private delivery routes',
             [('municipal','Municipal'),('private','Private'),('other_public','Other public')]),
            ('heat', 'Heat context · adds flood / heat overlap', [('priority','Heat-priority classes'),('other','Other known classes')]),
            ('restrictions', 'Known infiltration exclusions · retain documented restrictions', [('infiltration_excluded','Confirmed excluded classes')]),
        ]
        for key, title, categories in groups:
            group = QGroupBox(title); group.setCheckable(True); group.setChecked(False)
            body = QWidget(); body_form = QFormLayout(body)
            picker = LayerPicker(); field = QgsFieldComboBox(); picker.combo.layerChanged.connect(field.setLayer)
            body_form.addRow('Polygon layer',picker); body_form.addRow('Source category field',field)
            mapping = {}
            for category,label in categories:
                widget = QLineEdit(); widget.setPlaceholderText('Exact source values, separated by ;')
                mapping[category] = widget; body_form.addRow(label,widget)
            body_form.addRow(self.note('Leave unverified or unknown categories unmapped. Use Source… to record provider, date, version and licence.'))
            layout = QVBoxLayout(group); layout.addWidget(body); body.setVisible(False)
            group.toggled.connect(body.setVisible)
            form.addRow(group); self.planning_inputs[key] = (group,picker,field,mapping)
        self.tabs.insertTab(1,self.planning_page,'2 · Optional planning context')
        self.messages.setText('Start with a flood depth layer and study boundary. Optional surface, ownership and heat layers add planning detail. '
                              'Results include flood action areas, conditional NbS concepts, references and next actions. Advanced mode retains detailed design qualification and MURIEL.')
        self.change_mode()

    def change_mode(self):
        engineering = self.mode.currentData() == 'engineering'
        self.tabs.removeTab(1)
        self.tabs.insertTab(1,self.advanced_tab if engineering else self.planning_page,
                            '2 · Evidence && MURIEL' if engineering else '2 · Optional planning context')
        for widget in (self.designs, self.period):
            widget.setVisible(engineering)
            label = self.input_form.labelForField(widget)
            if label:
                label.setVisible(engineering)
        self.run_button.setText('Run detailed qualification' if engineering else 'Create planning results')
        self.status.setText('Detailed evidence and physical combinations' if engineering else 'Planning mode · two required GIS inputs')

    def flood_changed(self, layer):
        super().flood_changed(layer)
        for widget in (self.depth_field, self.id_field):
            widget.setVisible(isinstance(layer, QgsVectorLayer))
            label = self.input_form.labelForField(widget)
            if label:
                label.setVisible(isinstance(layer, QgsVectorLayer))
        show_band = isinstance(layer, QgsRasterLayer) and layer.bandCount() > 1
        self.band.setVisible(show_band)
        label = self.input_form.labelForField(self.band)
        if label:
            label.setVisible(show_band)

    def use_configuration(self, path):
        from .configuration import resolve_config
        config = resolve_config(path)
        self.mode.setCurrentIndex(0 if config.get('mode') == 'planning' else 1)
        super().use_configuration(path)
        self.mode.setEnabled(False)
        self.planning_page.setEnabled(False)

    def reset_configuration(self):
        super().reset_configuration()
        self.mode.setEnabled(True); self.planning_page.setEnabled(True)

    def configuration(self):
        config = super().configuration()
        if self.loaded_path or self.mode.currentData() == 'engineering':
            return config
        config.update(mode='planning', planning={})
        # The detailed form remains independent; hidden advanced declarations
        # must not silently enter the shorter planning setup.
        config.update(evidence=[], raster_evidence=[], distance_evidence=[], derived_module_bases=[], combinations=[], ownership=None)
        config['policy'].update(profile_reviewed=False, profile_review_ref=None)
        config['groundwater_scenario_id'] = 'UNKNOWN_DESIGN_GROUNDWATER'
        config['vertical_datum'] = None
        config['muriel'] = {'enabled':False}
        for key,(group,picker,field,inputs) in self.planning_inputs.items():
            if not group.isChecked():
                continue
            spec = picker.spec()
            if not spec:
                raise ValueError(f'{key}: select a polygon layer or turn off this optional section.')
            mapping = {}
            for category,widget in inputs.items():
                for value in (v.strip() for v in widget.text().split(';') if v.strip()):
                    if value in mapping and mapping[value] != category:
                        raise ValueError(f'{key}: source value "{value}" has two category assignments.')
                    mapping[value] = category
            if not mapping or not field.currentField():
                raise ValueError(f'{key}: select the source category field and map at least one known source value.')
            spec.update(class_field=field.currentField(),mapping=mapping)
            if key == 'ownership':
                config['ownership'] = spec
            else:
                config['planning'][key] = spec
        return config

    def start_run(self):
        super().start_run()
        if self.running:
            self.mode.setEnabled(False); self.planning_page.setEnabled(False)

    def execute_run(self, source):
        try:
            super().execute_run(source)
        finally:
            self.mode.setEnabled(self.loaded_path is None)
            self.planning_page.setEnabled(self.loaded_path is None)
