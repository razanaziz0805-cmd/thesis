"""Guided preparation of input datasets, including incomplete source packages."""
from datetime import datetime
import html
import json
from pathlib import Path
import re
from uuid import uuid4

from qgis.PyQt.QtWidgets import (QApplication,QCheckBox,QComboBox,QDialog,QDoubleSpinBox,
    QFileDialog,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QProgressBar,QPushButton,
    QTableWidget,QTableWidgetItem,QTextBrowser,QVBoxLayout,QWidget)
from qgis.PyQt.QtCore import QTimer,QUrl
from qgis.PyQt.QtGui import QDesktopServices
from osgeo import ogr

from .preparation import prepare
from .runtime import RunCancelled


class PreparationDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('Prepare GIS inputs · CRS, clip and grid');self.resize(1160,820)
        self.running=False;self.cancelled=False;self.output=None
        layout=QVBoxLayout(self)
        note=QLabel('Create new prepared files and a QGIS review project. Known CRSs are transformed automatically. Missing or wrong CRS labels require a confirmed source CRS and reference. Original files are preserved.')
        note.setWordWrap(True);layout.addWidget(note)
        self.form_widget=QWidget();form=QFormLayout(self.form_widget);layout.addWidget(self.form_widget)
        self.boundary=self.path_row(form,'Study boundary file','Choose study boundary',False)
        self.boundary_layer=QLineEdit();self.boundary_layer.setPlaceholderText('Layer name if the file contains multiple layers')
        form.addRow('Boundary layer',self.boundary_layer)
        self.boundary_crs=QLineEdit();self.boundary_crs.setPlaceholderText('Optional, for example EPSG:25832; never inferred from coordinates')
        self.boundary_ref=QLineEdit();self.boundary_ref.setPlaceholderText('Dated source confirmation for an assigned/replaced CRS')
        form.addRow('Confirmed boundary source CRS',self.boundary_crs);form.addRow('Boundary CRS evidence',self.boundary_ref)
        self.geometry_only=QCheckBox('Allow a geometry-only boundary when .dbf is missing');form.addRow(self.geometry_only)
        self.master=self.path_row(form,'Master raster','Choose master grid raster',False)
        self.target=QLineEdit('EPSG:25832');form.addRow('Target projected CRS',self.target)
        self.cell=QDoubleSpinBox();self.cell.setRange(0,10000);self.cell.setDecimals(3);self.cell.setSpecialValueText('Preserve native master grid');form.addRow('Cell size (metres; 0 = native)',self.cell)
        self.buffer=QDoubleSpinBox();self.buffer.setRange(0,10000);self.buffer.setValue(100);self.buffer.setSuffix(' m');form.addRow('Vector search extension',self.buffer)
        self.folder=self.path_row(form,'Workspace folder','Choose preparation workspace',True)
        self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels(['Source file','Layer','Raster kind','Resampling','Confirmed source CRS','CRS/grid evidence reference','Repair invalid','Geometry only'])
        layout.addWidget(self.table,1)
        self.add_button=QPushButton('Add input files…');self.add_button.clicked.connect(self.add_files);layout.addWidget(self.add_button)
        help_=QLabel('Point/line datasets remain points/lines. Raster values and units are preserved. Categorical data use nearest/mode; flood-grid changes require a justification. Finer output cells do not create finer source information.')
        help_.setWordWrap(True);layout.addWidget(help_)
        self.messages=QTextBrowser();self.messages.setMaximumHeight(115);layout.addWidget(self.messages)
        self.progress=QProgressBar();layout.addWidget(self.progress)
        buttons=QHBoxLayout();self.run_button=QPushButton('Prepare inputs');self.run_button.clicked.connect(self.start)
        self.cancel_button=QPushButton('Cancel');self.cancel_button.setEnabled(False);self.cancel_button.clicked.connect(self.cancel)
        self.open_button=QPushButton('Open prepared folder');self.open_button.setEnabled(False);self.open_button.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output))))
        for widget in (self.run_button,self.cancel_button,self.open_button):buttons.addWidget(widget)
        layout.addLayout(buttons)

    def path_row(self,form,label,title,directory):
        widget=QWidget();row=QHBoxLayout(widget);row.setContentsMargins(0,0,0,0);field=QLineEdit();button=QPushButton('Browse…');row.addWidget(field,1);row.addWidget(button)
        def browse():
            path=QFileDialog.getExistingDirectory(self,title) if directory else QFileDialog.getOpenFileName(self,title,'','GIS data (*.gpkg *.shp *.tif *.tiff);;All files (*)')[0]
            if path:field.setText(path)
        button.clicked.connect(browse);form.addRow(label,widget);return field

    def add_files(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Select input files','','GIS data (*.gpkg *.shp *.tif *.tiff)')
        for path in paths:self.add_path(path)

    def add_path(self,path,layer=''):
        path=Path(path);row=self.table.rowCount();self.table.insertRow(row)
        if path.suffix.lower()=='.gpkg' and not layer:
            source=ogr.Open(str(path),0)
            if source and source.GetLayerCount()==1:layer=source.GetLayer(0).GetName()
        for column,text in [(0,str(path)),(1,layer),(4,''),(5,'')]:self.table.setItem(row,column,QTableWidgetItem(text))
        kind=QComboBox();kind.addItems(['continuous','categorical','flood_depth']);kind.setEnabled(path.suffix.lower() in ('.tif','.tiff'));self.table.setCellWidget(row,2,kind)
        method=QComboBox();method.addItems(['near','mode','bilinear','average','max']);method.setEnabled(kind.isEnabled());self.table.setCellWidget(row,3,method)
        for column in (6,7):self.table.setCellWidget(row,column,QCheckBox())
        self.table.resizeColumnsToContents()

    def job(self):
        if not self.boundary.text().strip() or not self.folder.text().strip():raise ValueError('Choose the study boundary and workspace folder.')
        boundary={'path':self.boundary.text().strip(),'allow_geometry_only':self.geometry_only.isChecked()}
        if self.boundary_layer.text().strip():boundary['layer']=self.boundary_layer.text().strip()
        if self.boundary_crs.text().strip():boundary.update(source_crs=self.boundary_crs.text().strip(),crs_evidence_ref=self.boundary_ref.text().strip())
        datasets=[]
        for row in range(self.table.rowCount()):
            path=self.table.item(row,0).text();raster=Path(path).suffix.lower() in ('.tif','.tiff')
            ident=re.sub('[^A-Za-z0-9_]','_',Path(path).stem)
            spec={'id':'data_'+str(row)+'_'+ident,'path':path,'type':'raster' if raster else 'vector',
                  'repair_invalid':self.table.cellWidget(row,6).isChecked(),'allow_geometry_only':self.table.cellWidget(row,7).isChecked()}
            layer=self.table.item(row,1).text().strip();source=self.table.item(row,4).text().strip();ref=self.table.item(row,5).text().strip()
            if layer:spec['layer']=layer
            if source:spec.update(source_crs=source,crs_evidence_ref=ref)
            if raster:spec.update(kind=self.table.cellWidget(row,2).currentText(),resampling=self.table.cellWidget(row,3).currentText(),resampling_evidence_ref=ref or None)
            datasets.append(spec)
        if not datasets:raise ValueError('Add at least one input file.')
        job={'study_area':boundary,'target_crs':self.target.text().strip(),'search_buffer_m':self.buffer.value(),
             'datasets':datasets,'output_dir':str(Path(self.folder.text()).resolve()/('prepared_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid4().hex[:6]))}
        if any(s['type']=='raster' for s in datasets):
            if not self.master.text().strip():raise ValueError('Choose a master raster for grid origin and resolution.')
            master=next((dict(s) for s in datasets if Path(s['path']).resolve()==Path(self.master.text()).resolve()),{'path':self.master.text().strip()})
            job['grid']={'master':master}
            if self.cell.value():job['grid']['cell_size_m']=self.cell.value()
        return job

    def start(self):
        if self.running:return
        try:job=self.job()
        except Exception as exc:self.messages.setPlainText(str(exc));return
        self.running=True;self.cancelled=False;self.form_widget.setEnabled(False);self.table.setEnabled(False)
        self.run_button.setEnabled(False);self.add_button.setEnabled(False);self.cancel_button.setEnabled(True);self.open_button.setEnabled(False)
        QTimer.singleShot(0,lambda:self.execute(job))

    def execute(self,job):
        def progress(percent,message):self.progress.setValue(int(percent));self.messages.setPlainText(message);QApplication.processEvents()
        def cancelled():QApplication.processEvents();return self.cancelled
        try:
            self.output=prepare(job,progress,cancelled);self.open_button.setEnabled(True)
            self.messages.setHtml('Prepared: '+html.escape(str(self.output))+'<br>Open <b>prepared_inputs.qgz</b> to review alignment and coverage. The manifest records source resolution, transformations, unknowns and repairs. Preparation does not certify suitability.')
        except (RunCancelled,Exception) as exc:self.messages.setPlainText(str(exc))
        finally:
            self.running=False;self.form_widget.setEnabled(True);self.table.setEnabled(True);self.run_button.setEnabled(True);self.add_button.setEnabled(True);self.cancel_button.setEnabled(False)

    def cancel(self):self.cancelled=True

    def reject(self):
        if self.running:self.cancel()
        else:super().reject()
