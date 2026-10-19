"""Add this script through QGIS Processing Toolbox → Scripts → Add Script.

The repository folder is an explicit input so copying this file to the QGIS
profile does not break module discovery. Runs in the GUI thread for map layouts.
"""
import sys
from pathlib import Path
from qgis.core import (
    QgsProcessingAlgorithm, QgsProcessingOutputFile, QgsProcessingOutputHtml,
    QgsProcessingParameterBoolean, QgsProcessingParameterFile,
)


class NbsOpportunityStageOne(QgsProcessingAlgorithm):
    def name(self):
        return 'nbs_opportunity_stage_one'

    def displayName(self):
        return 'NbS Stage 1 · auditable opportunity maps'

    def group(self):
        return 'Thesis · NRW NbS'

    def groupId(self):
        return 'thesis_nrw_nbs'

    def createInstance(self):
        return NbsOpportunityStageOne()

    def flags(self):
        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def shortHelpString(self):
        return ('Run Stage 1 using a registered JSON configuration. Creates a new output folder, '
                'GeoPackage, QGIS project and optional map atlas. Existing projects and outputs '
                'are preserved. Missing evidence stays conditional. No hydraulic simulation.')

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile('REPOSITORY', 'Folder containing stage1/ and config/', behavior=QgsProcessingParameterFile.Folder))
        self.addParameter(QgsProcessingParameterFile('CONFIG', 'Stage 1 JSON configuration', extension='json'))
        self.addParameter(QgsProcessingParameterBoolean('EXPORT_MAPS', 'Export PNG maps and PDF atlas', defaultValue=True))
        self.addOutput(QgsProcessingOutputFile('PROJECT', 'QGIS project'))
        self.addOutput(QgsProcessingOutputHtml('REPORT', 'Stage 1 report'))

    def processAlgorithm(self, parameters, context, feedback):
        root = Path(self.parameterAsFile(parameters, 'REPOSITORY', context)).resolve()
        if not (root / 'stage1' / 'gis.py').exists():
            raise ValueError('Choose the repository folder containing stage1/gis.py')
        sys.path.insert(0, str(root))
        try:
            from stage1.gis import run
            feedback.pushInfo('Evaluating spatial evidence and rule gates; no hydraulic performance is inferred.')
            output = run(self.parameterAsFile(parameters, 'CONFIG', context), self.parameterAsBool(parameters, 'EXPORT_MAPS', context))
            return {'PROJECT': str(output / 'stage1.qgz'), 'REPORT': str(output / 'report.html')}
        finally:
            sys.path.remove(str(root))
