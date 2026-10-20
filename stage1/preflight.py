"""Read-only input checks with actionable messages, before expensive analysis."""
from dataclasses import asdict, dataclass, field
import math
from pathlib import Path

from .configuration import input_specs, load_data, resolve_config, structure_errors


@dataclass
class CheckResult:
    issues: list = field(default_factory=list)
    facts: dict = field(default_factory=dict)

    @property
    def ok(self):
        return not any(i['level'] == 'ERROR' for i in self.issues)

    def add(self, level, input_, message, action=''):
        self.issues.append({'level': level, 'input': input_, 'message': message, 'action': action})

    def as_dict(self):
        return {'ok': self.ok, **asdict(self)}

    def text(self):
        lines = ['Ready to run.' if self.ok else 'Correct the following errors before running.']
        for issue in self.issues:
            lines.append(f"[{issue['level']}] {issue['input']}: {issue['message']}" + (f" Action: {issue['action']}" if issue['action'] else ''))
        for key, value in self.facts.items():
            lines.append(f'{key}: {value}')
        return '\n'.join(lines)


def inspect_config(source, base_dir=None):
    result = CheckResult()
    try:
        data = load_data(source)
    except ValueError as exc:
        result.add('ERROR', 'Configuration', str(exc), 'Select a readable JSON configuration.')
        return result
    errors = structure_errors(data)
    for error in errors:
        result.add('ERROR', 'Configuration', error, 'Update this setting in the setup panel or configuration.')
    if errors:
        return result
    config = resolve_config(data, base_dir or (Path(source).resolve().parent if not isinstance(source, dict) else None))
    if (config.get('preparation') or {}).get('enabled') is True:
        from .preparation import check_run_sources
        for level,role,message,action in check_run_sources(config):result.add(level,role,message,action)
        result.facts['Preparation']='Enabled: source checks now; full field/grid checks after documented preparation.'
        result.facts['Output folder']=config['output_dir']
        return result
    from osgeo import gdal
    from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsVectorLayer, QgsWkbTypes
    crs = QgsCoordinateReferenceSystem(config.get('crs', 'EPSG:25832'))
    if not crs.isValid() or crs.isGeographic() or crs.mapUnits() != Qgis.DistanceUnit.Meters:
        result.add('ERROR', 'Processing CRS', 'A projected CRS in metres is required.', 'Use EPSG:25832 for this NRW workflow.')
    output = Path(config['output_dir'])
    if output.exists():
        result.add('ERROR', 'Output folder', f'Already exists: {output}', 'Choose a new run folder; earlier results are preserved.')
    master, boundary = None, None
    for role, spec in input_specs(config):
        path = Path(spec['path'])
        if not path.is_file():
            result.add('ERROR', role, f'File does not exist: {path}', 'Select the saved local GeoTIFF or vector file.')
            continue
        raster = (role == 'flood' and spec['type'] == 'raster') or role.startswith('raster_evidence')
        if raster:
            try:
                ds = gdal.Open(str(path))
                if ds is None:
                    raise ValueError('Raster cannot be opened.')
                band = spec.get('band', 1)
                if isinstance(band, bool) or not isinstance(band, int) or not 1 <= band <= ds.RasterCount:
                    raise ValueError(f'Band {band} is unavailable; this raster has {ds.RasterCount} band(s).')
                source_crs = QgsCoordinateReferenceSystem()
                source_crs.createFromWkt(ds.GetProjection())
                gt = ds.GetGeoTransform()
                if source_crs != crs or gt[2] or gt[4] or gt[1] <= 0 or gt[5] >= 0:
                    raise ValueError('Raster CRS or orientation differs from the configured north-up master grid. Reproject explicitly and document resampling.')
                info = (ds.RasterXSize, ds.RasterYSize, tuple(gt))
                if role == 'flood':
                    master = info
                    result.facts['Source grid'] = f'{info[0]} × {info[1]} cells; {gt[1]:g} × {abs(gt[5]):g} m'
                    if ds.GetRasterBand(band).GetNoDataValue() is None:
                        result.add('WARNING', role, 'No NoData value is declared.', 'Confirm whether all cells represent known depths.')
                elif master is None or info[:2] != master[:2] or any(abs(a-b) > 1e-8 for a,b in zip(gt,master[2])):
                    raise ValueError('Evidence raster must match the master-grid dimensions, origin and cell size exactly.')
                ds = None
            except (ValueError, RuntimeError) as exc:
                result.add('ERROR', role, str(exc), 'Correct the raster selection or prepare an explicitly aligned input.')
        else:
            uri = str(path) + ('|layername=' + spec['layer'] if spec.get('layer') else '')
            layer = QgsVectorLayer(uri, role, 'ogr')
            if not layer.isValid() or not layer.crs().isValid():
                result.add('ERROR', role, 'Layer cannot be read or has no defined CRS.', 'Choose the correct layer in the file and confirm its CRS.')
                continue
            expected = QgsWkbTypes.LineGeometry if role == 'muriel.routes' else QgsWkbTypes.PolygonGeometry
            if not role.startswith('distance_evidence') and layer.geometryType() != expected:
                result.add('ERROR', role, 'Unexpected geometry type.', 'Use directed route lines.' if role == 'muriel.routes' else 'Use polygon footprints rather than points or centrelines.')
            required = []
            if role == 'flood':
                required = [spec.get('id_field', 'unit_id'), spec['depth_field']]
                depth = layer.fields().lookupField(spec['depth_field'])
                if depth >= 0 and not layer.fields()[depth].isNumeric():
                    result.add('ERROR', role, 'Flood depth field is not numeric.', 'Select a numeric depth field in centimetres or metres.')
            elif role == 'ownership':
                required = [spec.get('class_field', 'owner_class')]
                if not spec.get('mapping'):
                    result.add('ERROR', role, 'Ownership category mapping is missing.', 'Map source values to municipal, private, other_public or unknown.')
            elif role.startswith('evidence['):
                required = list((spec.get('fields') or {}).values())
                if spec.get('join', 'id') == 'id':
                    required += [spec.get('id_field', 'unit_id')]
            elif role.startswith('distance_evidence') and not str(spec.get('field', '')).endswith('_distance_m'):
                result.add('ERROR', role, 'Distance target field must end in _distance_m.', 'Select the relevant surveyed distance field.')
            elif role == 'muriel.municipal_land' and spec.get('class_field'):
                required = [spec['class_field']]
                if not spec.get('municipal_values'):
                    result.add('ERROR', role, 'Municipal categories are not selected.', 'Specify the source category values for municipal land.')
            elif role == 'muriel.usable_space':
                required = [spec.get('id_field', 'destination_id'), spec.get('usable_field', 'usable')]
            elif role == 'muriel.routes':
                required = ['hotspot_id', 'destination_id']
            missing = [f for f in required if f not in layer.fields().names()]
            if missing:
                result.add('ERROR', role, 'Missing fields: ' + ', '.join(missing), 'Correct the field mapping or select the appropriate layer.')
            if role == 'study_area' and crs.isValid() and layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                try:
                    boundary = QgsCoordinateTransform(layer.crs(), crs, QgsProject.instance()).transformBoundingBox(layer.extent())
                except Exception as exc:
                    result.add('ERROR', role, f'Cannot transform the study extent: {exc}')
        meta = spec.get('metadata') or {}
        if any(not meta.get(k) or meta[k] == 'REQUIRED' for k in ('provider', 'date', 'version', 'license')):
            result.add('WARNING', role, 'Source metadata are incomplete.', 'Record provider, date, version and licence before reporting thesis results.')
        if role.startswith('muriel.') and spec.get('coverage_complete') is not True:
            result.add('WARNING', role, 'Inventory coverage is unconfirmed.', 'Verify coverage through the destination search extension; incomplete coverage stays conditional.')
    if master and boundary:
        w,h,gt = master
        x0=max(0,math.floor((boundary.xMinimum()-gt[0])/gt[1])); x1=min(w,math.ceil((boundary.xMaximum()-gt[0])/gt[1]))
        y0=max(0,math.floor((boundary.yMaximum()-gt[3])/gt[5])); y1=min(h,math.ceil((boundary.yMinimum()-gt[3])/gt[5]))
        count=max(0,x1-x0)*max(0,y1-y0)
        result.facts['Maximum cells in study bounding box'] = count
        result.facts['Selected NbS designs'] = len(config['designs'])
        if count == 0:
            result.add('ERROR', 'Spatial extent', 'Flood raster and study boundary do not overlap.', 'Check layer selection and spatial references.')
        elif count > config.get('max_units',250000):
            result.add('ERROR', 'Analysis size', f'{count:,} cells exceeds the configured limit.', 'Partition the study or supply a justified polygon partition; no automatic coarsening is applied.')
    if not config['policy']['profile_reviewed']:
        result.add('WARNING', 'Rule profile', 'Local technical and authority review is outstanding.', 'Final admissibility remains conditional until the review is referenced.')
    if not config.get('evidence') and not config.get('raster_evidence'):
        result.add('WARNING', 'NbS evidence', 'No site/groundwater evidence is registered.', 'You can produce the need map; unsupported NbS gates remain conditional.')
    m = config.get('muriel') or {}
    if m.get('enabled'):
        for key in ('receptors', 'municipal_land', 'roads', 'usable_space'):
            if not m.get(key):
                result.add('WARNING', 'MURIEL', f'{key.replace("_", " ")} input is missing.', 'Add the inventory to resolve the public-space screening evidence gaps.')
    result.facts['Output folder'] = str(output)
    result.facts['Geometry checks'] = 'Full geometry, overlap and evidence checks also run during analysis.'
    return result
