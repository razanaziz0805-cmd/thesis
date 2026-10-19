from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsApplication


class StageOnePlugin:
    def __init__(self, iface):
        self.iface=iface
        self.dialog=None

    def initGui(self):
        self.action=QAction('NbS Stage 1 · opportunity mapping',self.iface.mainWindow())
        self.action.setIcon(QgsApplication.getThemeIcon('/mActionOptions.svg'))
        self.action.triggered.connect(self.open)
        self.iface.addPluginToMenu('&NbS planning',self.action)
        self.iface.addToolBarIcon(self.action)

    def open(self):
        from .stage1.gui import StageOneDialog
        if self.dialog is None:
            self.dialog=StageOneDialog(self.iface,self.iface.mainWindow())
        self.dialog.show(); self.dialog.raise_(); self.dialog.activateWindow()

    def unload(self):
        if self.dialog and self.dialog.running:
            self.dialog.request_cancel()
        if self.dialog: self.dialog.close()
        self.iface.removePluginMenu('&NbS planning',self.action)
        self.iface.removeToolBarIcon(self.action)
