"""QGIS/GDAL I/O, conservative spatial joins, GeoPackage and map production."""

import csv
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import re
from pathlib import Path
import sqlite3

import numpy as np
from osgeo import gdal
from qgis.PyQt.QtCore import QVariant, Qt
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    Qgis, QgsApplication, QgsCategorizedSymbolRenderer, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsEditorWidgetSetup, QgsFeature, QgsField, QgsFillSymbol,
    QgsGeometry, QgsLayoutExporter, QgsLayoutItemLabel, QgsLayoutItemLegend,
    QgsLayoutItemMap, QgsLayoutItemScaleBar, QgsLayoutPoint, QgsLayoutSize,
    QgsPrintLayout, QgsProject, QgsRectangle, QgsRelation, QgsRendererCategory,
    QgsSpatialIndex, QgsVectorFileWriter, QgsVectorLayer, QgsWkbTypes, QgsLineSymbol,
)

from .catalogue import DESIGNS, SOURCES
from .engine import aggregate, evaluate_combination, evaluate_design, groundwater, intervention_need, number, truth, validate_policy

gdal.UseExceptions()

PALETTE = {
    "ADMISSIBLE": ("#23766a", "Admissible · screening gates met"),
    "CONDITIONAL": ("#e8b04a", "Conditional · evidence / decision needed"),
    "FAIL": ("#b94c52", "Fail · applicable gate not met"),
    "NOT_APPLICABLE": ("#b5bdc6", "Not applicable"),
    "YES": ("#245e86", "Intervention screen · depth ≥ threshold"),
    "NO": ("#e1e9ee", "Depth below threshold"),
    "UNKNOWN": ("#b5bdc6", "Unknown / NoData"),
    "municipal": ("#218a88", "Municipal ownership"),
    "private": ("#8366ac", "Private ownership"),
    "other_public": ("#6c94b4", "Other public owner"),
    "mixed": ("#d7b36c", "Mixed ownership · see area shares"),
    "conflict": ("#b94c52", "Conflicting overlapping ownership"),
    "unknown": ("#b5bdc6", "Unknown ownership"),
    'QUALIFYING_HOTSPOT': ('#245e86', 'Area and maximum-depth criteria met'),
    'DEPTH_INCLUDED': ('#245e86', 'Inside registered MURIEL depth mask'),
    'DEPTH_EXCLUDED': ('#e7ebee', 'Outside registered MURIEL depth mask'),
    'DEPTH_UNKNOWN': ('#a488b4', 'Unknown source depth / NoData'),
    'EXTENT_UNCERTAIN': ('#a488b4', 'Flood extent / NoData evidence gap'),
    'BELOW_SCREEN': ('#dce2e7', 'Below local hotspot screen'),
    'PROTECT_RETENTION': ('#20766b', 'Protect existing retention'),
    'RETROFIT_CANDIDATE': ('#286b9a', 'Retrofit · route evidence supplied'),
    'ROUTING_INVESTIGATION': ('#e8b04a', 'Investigate topography / flow route'),
    'NO_DESTINATION': ('#ac6570', 'No usable destination · alternatives'),
    'OUTSIDE_PRIORITY': ('#909ba7', 'Outside local adjacency / land screen'),
    'ROUTE_UNSUITABLE': ('#b9474d', 'Assessed route incompatible'),
    'EVIDENCE_GAP': ('#9b82ad', 'Evidence gap · retain conditional'),
    'USABLE_SPACE': ('#70a989', 'Usable municipal non-road space'),
    'VERIFIED_ROUTE': ('#23766a', 'Route evidence supplied'),
    'REJECTED_ROUTE': ('#b94c52', 'Incompatible assessed route'),
    'UNVERIFIED_ROUTE': ('#e8b04a', 'Route assessment incomplete'),
    'PROXIMITY_ONLY': ('#c48e28', 'Proximity only · no flow proof'),
    'MUNICIPAL_CONTEXT': ('#e7eee3', 'Municipal land · context'),
    'FLOOD_CONTEXT': ('#dae5ee', 'Flood footprint · context'),
    'ROAD_CONTEXT': ('#ede8df', 'Road footprint · context'),
    'BUILDING_CONTEXT': ('#79858e', 'Building / receptor · context'),
}


def checksum(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def clean(value):
    if value is None or (hasattr(value, "isNull") and value.isNull()):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def attrs(feature):
    return {f.name(): clean(feature[f.name()]) for f in feature.fields()}


def load_vector(spec, target_crs, allow_empty=False):
    uri = str(spec["path"]) + ("|layername=" + spec["layer"] if spec.get("layer") else "")
    layer = QgsVectorLayer(uri, spec.get("layer", Path(spec["path"]).stem), "ogr")
    if not layer.isValid() or not layer.crs().isValid():
        raise ValueError(f"Unreadable vector or undefined CRS: {uri}")
    transform = QgsCoordinateTransform(layer.crs(), target_crs, QgsProject.instance())
    result = []
    for f in layer.getFeatures():
        geom = QgsGeometry(f.geometry())
        if geom.isEmpty() or not geom.isGeosValid():
            raise ValueError(f"Empty / invalid geometry in {uri}, feature {f.id()}; repair and review the source explicitly")
        if layer.crs() != target_crs:
            geom.transform(transform)
        result.append((geom, attrs(f)))
    if not result and not allow_empty:
        raise ValueError(f"No features in {uri}")
    return result


def indexed(features):
    index, records = QgsSpatialIndex(), {}
    for i, (geom, a) in enumerate(features):
        f = QgsFeature(i)
        f.setGeometry(geom)
        index.addFeature(f)
        records[i] = (geom, a)
    return index, records


def ownership(geom, index, records, field, mapping):
    pieces = {k: [] for k in ("municipal", "private", "other_public", "unknown")}
    for fid in index.intersects(geom.boundingBox()):
        other, a = records[fid]
        intersection = geom.intersection(other)
        if not intersection.isEmpty() and intersection.area() > 1e-8:
            label = mapping.get(str(a.get(field)), "unknown")
            if label not in pieces:
                raise ValueError(f"Unsupported ownership class {label}")
            pieces[label].append(intersection)
    unions = {k: QgsGeometry.unaryUnion(v) for k, v in pieces.items() if v}
    all_pieces = [g for v in pieces.values() for g in v]
    covered = QgsGeometry.unaryUnion(all_pieces).area() if all_pieces else 0.0
    duplicate_area = max(0.0, sum(g.area() for g in all_pieces) - covered)
    area = geom.area()
    # Overlap is explicitly reported even for repeated parcels of the same class.
    fractions = {k: unions[k].area() / area if k in unions else 0.0 for k in pieces}
    fractions["unknown"] += max(0.0, 1 - covered / area)
    known = [k for k in ("municipal", "private", "other_public") if fractions[k] > 1e-6]
    if duplicate_area > max(1e-6, area * 1e-6):
        status = "conflict"
    elif not known:
        status = "unknown"
    elif len(known) == 1 and fractions[known[0]] >= 1 - 1e-6:
        status = known[0]
    else:
        status = "mixed"
    return {"owner_class": status, **{k + "_fraction": v for k, v in fractions.items()}, "ownership_overlap_m2": duplicate_area}


def join_evidence(geom, index, records, fields):
    """Conservative area overlay. Missing coverage/mixed values never pass.

    A known prohibition anywhere in the unit is retained. Otherwise mixed fields
    remain unknown; refine/split units for a less conservative site screen.
    """
    intersections = []
    for fid in index.intersects(geom.boundingBox()):
        other, a = records[fid]
        cut = geom.intersection(other)
        if not cut.isEmpty() and cut.area() > 1e-8:
            intersections.append((cut, a))
    result = {}
    for dest, origin in fields.items():
        usable = [(g, a.get(origin)) for g, a in intersections if a.get(origin) is not None]
        values = [v for _, v in usable]
        coverage = QgsGeometry.unaryUnion([g for g, _ in usable]).area() / geom.area() if usable else 0
        if dest == "protection_zone" and any(str(v).upper() in ("I", "II") for v in values):
            result[dest] = "I" if "I" in values else "II"
        elif dest in ("receiving_ground_clean", "soil_infiltration_ok", "runoff_quality_ok") and any(truth(v) is False for v in values):
            result[dest] = False
        elif coverage < 1 - 1e-6 or not values:
            result[dest] = None
        elif len({json.dumps(v, sort_keys=True) for v in values}) == 1:
            result[dest] = values[0]
        elif dest.endswith("distance_m") or dest.startswith("module_base_elevation_m__"):
            result[dest] = min(number(v) for v in values) if all(number(v) is not None for v in values) else None
        elif dest in ("design_groundwater_elevation_m", "groundwater_uncertainty_m"):
            result[dest] = max(number(v) for v in values) if all(number(v) is not None for v in values) else None
        else:
            result[dest] = None
    return result


def read_units(config, crs):
    flood = config["flood"]
    units = []
    factor = {"m": 1.0, "cm": .01}.get(flood.get("units"))
    if factor is None:
        raise ValueError("Flood depth units must explicitly be m or cm")
    if not config.get("study_area"):
        raise ValueError("A documented study-area polygon is required")
    aoi = QgsGeometry.unaryUnion([g for g, _ in load_vector(config["study_area"], crs)])
    if aoi.area() <= 0:
        raise ValueError("Study area must be polygonal")
    maximum = config.get("max_units", 250000)
    if flood["type"] == "vector":
        seen = set()
        for geom, a in load_vector(flood, crs):
            if flood['depth_field'] not in a:
                raise ValueError(f'Configured flood depth field is absent: {flood["depth_field"]}')
            if not geom.intersects(aoi):
                continue
            geom = geom.intersection(aoi)
            if geom.area() <= 1e-8:
                continue
            uid = a.get(flood.get("id_field", "unit_id"))
            if uid is None or not str(uid).strip() or str(uid) in seen:
                raise ValueError("Vector analysis units require unique, nonempty IDs")
            seen.add(str(uid))
            depth = number(a.get(flood["depth_field"]))
            a.update(unit_id=str(uid), flood_depth_m=None if depth is None or depth < 0 else depth * factor)
            units.append({"geometry": geom, "attrs": a})
        # Input polygons are a partition, not overlapping candidate footprints.
        idx, rec = indexed([(u["geometry"], u["attrs"]) for u in units])
        for i, u in enumerate(units):
            for other in idx.intersects(u["geometry"].boundingBox()):
                if other > i and u["geometry"].intersection(rec[other][0]).area() > 1e-6:
                    raise ValueError("Flood analysis polygons overlap; use a nonoverlapping analysis grid / partition")
        grid = {"type": "vector_partition", "count": len(units)}
    elif flood["type"] == "raster":
        ds = gdal.Open(str(flood["path"]))
        if ds is None:
            raise ValueError("Flood raster cannot be opened")
        raster_crs = QgsCoordinateReferenceSystem()
        raster_crs.createFromWkt(ds.GetProjection())
        if raster_crs != crs:
            raise ValueError("Reproject the flood raster explicitly to the configured CRS; depth resampling must be documented, not silent")
        gt = ds.GetGeoTransform()
        if gt[2] or gt[4] or gt[1] <= 0 or gt[5] >= 0:
            raise ValueError("Use a north-up master raster with positive x and negative y pixel sizes")
        box = aoi.boundingBox()
        x0 = max(0, math.floor((box.xMinimum() - gt[0]) / gt[1]))
        x1 = min(ds.RasterXSize, math.ceil((box.xMaximum() - gt[0]) / gt[1]))
        y0 = max(0, math.floor((box.yMaximum() - gt[3]) / gt[5]))
        y1 = min(ds.RasterYSize, math.ceil((box.yMinimum() - gt[3]) / gt[5]))
        if x1 <= x0 or y1 <= y0:
            raise ValueError('No flood raster cells intersect the study-area extent')
        if max(0, x1 - x0) * max(0, y1 - y0) > maximum:
            raise ValueError(f"Raster exceeds {maximum} analysis cells; partition the domain / supply candidate polygons rather than silently coarsening")
        band = ds.GetRasterBand(flood.get("band", 1))
        nodata = band.GetNoDataValue()
        for row in range(y0, y1):
            values = band.ReadAsArray(x0, row, x1 - x0, 1)[0]
            for offset, v in enumerate(values):
                col = x0 + offset
                x, top = gt[0] + col * gt[1], gt[3] + row * gt[5]
                geom = QgsGeometry.fromRect(QgsRectangle(x, top + gt[5], x + gt[1], top)).intersection(aoi)
                if geom.area() <= 1e-8:
                    continue
                value = number(v)
                if value is None or value < 0 or (nodata is not None and (v == nodata or (math.isnan(nodata) and math.isnan(v)))):
                    value = None
                units.append({"geometry": geom, "attrs": {"unit_id": f"r{row:07d}_c{col:07d}", "grid_row": row, "grid_col": col, "flood_depth_m": None if value is None else value * factor}})
        grid = {"type": "raster_cells", "geotransform": gt, "width": ds.RasterXSize, "height": ds.RasterYSize,
                "pixel_size_m": [gt[1], abs(gt[5])], "depth_units": flood["units"], "nodata": nodata, "resampling": "none"}
        ds = None
    else:
        raise ValueError("flood.type must be raster or vector")
    if not units:
        raise ValueError("No analysis units intersect the study area")
    if len(units) > maximum:
        raise ValueError(f"More than {maximum} units; partition the domain")
    for u in units:
        u["attrs"]["area_m2"] = u["geometry"].area()
    return units, aoi, grid


def derived_evidence(config, units, grid, crs):
    """Read explicitly aligned covariate rasters and surveyed distance layers.

    No hidden interpolation. Numeric design base depths remain assumptions until
    design_geometry_confirmed and the other design evidence are supplied.
    """
    reserved = {'unit_id', 'area_m2', 'flood_depth_m', 'grid_row', 'grid_col'}
    for spec in config.get('raster_evidence', []):
        if grid['type'] != 'raster_cells':
            raise ValueError('Aligned raster evidence requires the raster-cell analysis mode; use polygon evidence joins for vector units')
        field = spec['field']
        if field in reserved:
            raise ValueError('Raster evidence may not overwrite analysis identifiers / flood values')
        ds = gdal.Open(spec['path'])
        source_crs = QgsCoordinateReferenceSystem()
        source_crs.createFromWkt(ds.GetProjection())
        if source_crs != crs or ds.RasterXSize != grid['width'] or ds.RasterYSize != grid['height'] or not np.allclose(ds.GetGeoTransform(), grid['geotransform'], rtol=0, atol=1e-8):
            raise ValueError(f'Raster evidence must match the master-grid CRS, origin, extent and cell size: {spec["path"]}')
        band = ds.GetRasterBand(spec.get('band', 1))
        nodata = band.GetNoDataValue()
        factor = {'m': 1., 'cm': .01, 'category': 1.}.get(spec.get('units'))
        if factor is None:
            raise ValueError('Raster evidence units must be explicitly m, cm or category')
        by_row = {}
        for u in units:
            by_row.setdefault(u['attrs']['grid_row'], []).append(u)
        for row, selected in by_row.items():
            start = min(u['attrs']['grid_col'] for u in selected)
            end = max(u['attrs']['grid_col'] for u in selected)
            values = band.ReadAsArray(start, row, end-start+1, 1)[0]
            for u in selected:
                raw = values[u['attrs']['grid_col'] - start]
                value = number(raw)
                if value is None or (nodata is not None and raw == nodata):
                    value = None
                elif spec['units'] == 'category':
                    value = spec.get('mapping', {}).get(str(int(value)) if value.is_integer() else str(value))
                else:
                    value *= factor
                u['attrs'][field] = value
        ds = None
    for spec in config.get('distance_evidence', []):
        field = spec['field']
        if field in reserved or not field.endswith('_distance_m'):
            raise ValueError('Distance evidence field must be an explicit *_distance_m field')
        features = load_vector(spec, crs)
        index = QgsSpatialIndex(flags=QgsSpatialIndex.FlagStoreFeatureGeometries)
        for i, (geom, _) in enumerate(features):
            f = QgsFeature(i)
            f.setGeometry(geom)
            index.addFeature(f)
        for u in units:
            nearest = index.nearestNeighbor(u['geometry'], 1)
            distance = min(u['geometry'].distance(index.geometry(i)) for i in nearest)
            # Incomplete inventories cannot establish absence of nearby assets.
            u['attrs'][field] = distance if spec.get('coverage_complete') is True else None
            u['attrs']['evidence_ref__' + field] = spec.get('evidence_ref') or 'MISSING_DISTANCE_SOURCE_REFERENCE'
    for spec in config.get('derived_module_bases', []):
        design, depth = spec.get('design'), number(spec.get('base_depth_m'))
        if design not in config['designs'] or not DESIGNS[design][2] or depth is None or depth < 0:
            raise ValueError('Module-base derivation needs a known infiltrating design and nonnegative base_depth_m')
        for u in units:
            surface = number(u['attrs'].get(spec.get('surface_field', 'surface_elevation_m')))
            u['attrs']['module_base_elevation_m__' + design] = None if surface is None else surface - depth
            u['attrs']['module_base_assumption_ref__' + design] = spec.get('evidence_ref', 'UNVERIFIED_DESIGN_DEPTH_ASSUMPTION')


def memory_layer(name, records, crs, polygon=True, geometry_type=None):
    layer = QgsVectorLayer(((geometry_type or 'MultiPolygon') + '?crs=' + crs.authid()) if polygon else 'None', name, 'memory')
    provider = layer.dataProvider()
    keys = list(dict.fromkeys(k for a, _ in records for k in a))
    # GIS output is a stable schema: numerical values stay numerical, long audit
    # strings stay strings. Boolean evidence is represented as integer 0/1.
    fields = []
    for k in keys:
        nonempty = [a[k] for a, _ in records if a.get(k) is not None]
        is_numeric = bool(nonempty) and all(isinstance(v, (int, float)) for v in nonempty)
        fields.append(QgsField(k, QVariant.Double if is_numeric else QVariant.String))
    provider.addAttributes(fields)
    layer.updateFields()
    batch = []
    for a, geom in records:
        f = QgsFeature(layer.fields())
        f.setAttributes([a.get(k) for k in keys])
        if polygon and geom is not None and not geom.isEmpty():
            g = QgsGeometry(geom)
            g.convertToMultiType()
            f.setGeometry(g)
        batch.append(f)
        if len(batch) >= 2000:
            if not provider.addFeatures(batch)[0]:
                raise RuntimeError(f"Failed to create features for {name}")
            batch = []
    if batch and not provider.addFeatures(batch)[0]:
        raise RuntimeError(f"Failed to create features for {name}")
    layer.updateExtents()
    return layer


def write_layer(path, layer, name, first=False):
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName, opts.layerName = "GPKG", name
    opts.fileEncoding = "UTF-8"
    opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile if first else QgsVectorFileWriter.CreateOrOverwriteLayer
    result = QgsVectorFileWriter.writeAsVectorFormatV3(layer, str(path), QgsProject.instance().transformContext(), opts)
    if result[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"GeoPackage write failed: {result}")


def summary(rows):
    return {
        "status": aggregate(rows),
        "reason_codes": "; ".join(d.rule_id for d in rows if d.status in ("FAIL", "CONDITIONAL")),
        "explanation": "\n\n".join(f"[{d.status}] {d.rule_id}: {d.reason}\nObserved: {d.observed}\nExpected: {d.expected}\nSource: {SOURCES[d.source_id]['citation']} | {SOURCES[d.source_id]['locator']}\n{SOURCES[d.source_id]['url']}\nEvidence: {d.evidence_ref}\nResponsible: {d.responsible_party}\nClose: {d.closure}" for d in rows),
        "source_ids": "; ".join(sorted({d.source_id for d in rows})),
    }


def add_attribute_table(db, name, records):
    if not records:
        return
    keys = list(records[0])
    db.execute(f'CREATE TABLE "{name}" (row_id INTEGER PRIMARY KEY, ' + ', '.join(f'"{k}" TEXT' for k in keys) + ')')
    db.executemany(f'INSERT INTO "{name}" (' + ','.join(f'"{k}"' for k in keys) + ') VALUES (' + ','.join('?' for _ in keys) + ')',
                   [[str(r[k]) if r[k] is not None else None for k in keys] for r in records])
    db.execute("INSERT INTO gpkg_contents(table_name,data_type,identifier,description,last_change) VALUES (?, 'attributes', ?, ?, ?)",
               (name, name, "Stage 1 audit register", datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')))
    # Complete the GDAL-maintained counts extension too. Otherwise opening the
    # first audit table can cause OGR to create counts while QGIS has read-only
    # no-lock connections open, switching journal modes underneath those reads.
    db.execute('INSERT INTO gpkg_ogr_contents(table_name,feature_count) VALUES (?,?)', (name, len(records)))
    for operation, delta in (('insert', '+'), ('delete', '-')):
        db.execute(f'CREATE TRIGGER "trigger_{operation}_feature_count_{name}" AFTER {operation.upper()} ON "{name}" BEGIN UPDATE gpkg_ogr_contents SET feature_count = feature_count {delta} 1 WHERE lower(table_name) = lower(\'{name}\'); END')


def csv_write(path, rows):
    if rows:
        with Path(path).open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
            w.writeheader()
            w.writerows(rows)


def styled_layer(gpkg, table, name, field="status", subset=None):
    # Use normal SQLite locking consistently across the many map-theme copies.
    # Mixing QGIS's automatic NOLOCK readers with a later WAL connection can
    # invalidate existing readers during project creation.
    layer = QgsVectorLayer(f"{gpkg}|layername={table}|option:NOLOCK=NO", name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Cannot reopen {table}")
    if subset:
        layer.setSubsetString(subset)
    categories = []
    for value, (color, label) in PALETTE.items():
        if layer.geometryType() == QgsWkbTypes.LineGeometry:
            symbol = QgsLineSymbol.createSimple({'line_color': color, 'line_width': '0.8',
                                                  'line_style': 'dash' if value in ('PROXIMITY_ONLY', 'UNVERIFIED_ROUTE') else 'solid'})
        else:
            symbol = QgsFillSymbol.createSimple({"color": color, "outline_color": "#ffffff", "outline_width": "0.12"})
        categories.append(QgsRendererCategory(value, symbol, label))
    layer.setRenderer(QgsCategorizedSymbolRenderer(field, categories))
    display = next((k for k in ('hotspot_label', 'connection_id', 'destination_id', 'unit_id', 'combination_id') if layer.fields().indexFromName(k) >= 0), None)
    if display:
        layer.setDisplayExpression('"' + display + '"')
    if layer.fields().indexFromName("explanation") >= 0:
        layer.setEditorWidgetSetup(layer.fields().indexFromName("explanation"), QgsEditorWidgetSetup("TextEdit", {"IsMultiline": True, "UseHtml": False}))
    tip_header = '<b>[% "' + display + '" %]</b>' if display else '<b>' + html.escape(name) + '</b>'
    tip_status = '[% "status" %]' if layer.fields().indexFromName('status') >= 0 else 'Context only'
    layer.setMapTipTemplate(tip_header + '<br>' + tip_status + '<br><pre>[% replace(replace(replace("explanation", \'&\', \'&amp;\'), \'<\', \'&lt;\'), \'>\', \'&gt;\') %]</pre>')
    label_field = 'context_label' if table == 'muriel_context' else display
    if table.startswith('muriel_') and label_field and table not in ('muriel_source_mask', 'muriel_hotspots', 'muriel_priority', 'muriel_connections'):
        from qgis.core import QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings, QgsVectorLayerSimpleLabeling
        labeling = QgsPalLayerSettings(); labeling.fieldName = label_field
        text_format = QgsTextFormat(); text_format.setFont(QFont('DejaVu Sans', 8)); text_format.setSize(8)
        buffer = QgsTextBufferSettings(); buffer.setEnabled(True); buffer.setSize(.7); buffer.setColor(QColor('white'))
        text_format.setBuffer(buffer); labeling.setFormat(text_format)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(labeling)); layer.setLabelsEnabled(True)
    return layer


def label_item(layout, text, x, y, width, height, size=10, color="#243e4a", bold=False):
    item = QgsLayoutItemLabel(layout)
    item.setText(text)
    item.setFont(QFont("DejaVu Sans", size, QFont.Bold if bold else QFont.Normal))
    item.setFontColor(QColor(color))
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(x, y))
    item.attemptResize(QgsLayoutSize(width, height))
    return item


def make_layout(project, layer, title, config, notes, extent, number_, context_layers=None):
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.pageCollection().pages()[0].setPageSize('A3', QgsLayoutItemMap.Landscape if hasattr(QgsLayoutItemMap, 'Landscape') else 1)
    layout.setName(f"{number_:02d} {title}")
    layout.renderContext().setDpi(180)
    demo = config.get("demo", False)
    header = "SYNTHETIC DEMONSTRATION · NOT A KÖLN-KALK RESULT" if demo else "STAGE 1 · SPATIAL OPPORTUNITY SCREEN"
    label_item(layout, header, 12, 7, 396, 8, 11, "#9b4248" if demo else "#23766a", True)
    label_item(layout, title, 12, 19, 393, 13, 20 if len(title) < 65 else 15, bold=True)
    label_item(layout, config['area_label'] + "  /  " + config['scenario_id'], 12, 35, 395, 8, 10)
    map_ = QgsLayoutItemMap(layout)
    layout.addLayoutItem(map_)
    map_.attemptMove(QgsLayoutPoint(12, 50))
    map_.attemptResize(QgsLayoutSize(264, 218))
    map_.setCrs(project.crs())
    map_.setLayers([layer, *(context_layers or [])])
    map_.setKeepLayerSet(True)
    rect = QgsRectangle(extent)
    rect.scale(1.10)
    map_.zoomToExtent(rect)
    map_.setFrameEnabled(True)
    map_.setFrameStrokeColor(QColor('#a5b6be'))
    label_item(layout, "N\n↑", 257, 53, 15, 22, 16, bold=True)
    legend = QgsLayoutItemLegend(layout)
    legend.setTitle("Map key")
    if layer.name().startswith('MURIEL'):
        from qgis.core import QgsLegendStyle
        legend.setStyleFont(QgsLegendStyle.SymbolLabel, QFont('DejaVu Sans', 9))
        legend.setStyleFont(QgsLegendStyle.Subgroup, QFont('DejaVu Sans', 9))
    legend.setLinkedMap(map_)
    legend.setAutoUpdateModel(False)
    legend.model().rootGroup().clear()
    legend.model().rootGroup().addLayer(layer)
    # Only display categories actually present in this map.
    present = {str(f[layer.renderer().classAttribute()]) for f in layer.getFeatures()}
    root = legend.model().rootGroup().children()[0]
    root.setUseLayerName(False)
    root.setName('Classification')
    from qgis.core import QgsMapLayerLegendUtils
    order = [i for i, c in enumerate(layer.renderer().categories()) if str(c.value()) in present]
    QgsMapLayerLegendUtils.setLegendNodeOrder(root, order)
    legend.model().refreshLayerLegend(root)
    layout.addLayoutItem(legend)
    legend.attemptMove(QgsLayoutPoint(285, 51))
    legend.attemptResize(QgsLayoutSize(117, 44))
    scale = QgsLayoutItemScaleBar(layout)
    scale.setStyle('Single Box')
    scale.setLinkedMap(map_)
    scale.applyDefaultSize()
    layout.addLayoutItem(scale)
    scale.attemptMove(QgsLayoutPoint(20, 250))
    is_muriel = layer.name().startswith('MURIEL')
    label_item(layout, "READ THIS MAP", 285, 125 if is_muriel else 111, 118, 8, 11, bold=True)
    label_item(layout, notes, 285, 137 if is_muriel else 123, 119, 78, 9)
    threshold = config['flood_threshold_m']
    metadata = (f"Scenario: {config['scenario_id']}\nNeed threshold: ≥{threshold * 100:g} cm\n"
                f"Horizontal CRS: {project.crs().authid()}\nGrid: {config.get('analysis_grid_description', 'See manifest')}\nVertical datum: {config.get('vertical_datum') or 'UNCONFIRMED'}\n"
                f"Rule profile: {config['policy']['profile_id']}\nRun: {config['run_id']}\n"
                "Source details: GeoPackage registers\nIdentify a feature for all rule decisions.")
    label_item(layout, metadata, 285, 224 if is_muriel else 208, 118, 49 if is_muriel else 65, 8)
    footer = "Synthetic inputs; all evidence and authority decisions are invented for software testing." if demo else "Screening only. No hydraulic benefit, structural certification or construction permission is established."
    if layer.name().startswith('MURIEL'):
        footer = 'Schwerdorf (2022), thesis §§4.4.2 / 5.5.3. Local planning screen; no infiltration or construction approval.' + (' SYNTHETIC DATA.' if demo else '')
    label_item(layout, footer, 12, 277, 390, 8, 9, '#9b4248' if demo else '#243e4a')
    label_item(layout, f"NbS opportunity workflow  |  Stage 1  |  Sheet {number_:02d}", 12, 287, 390, 7, 8)
    project.layoutManager().addLayout(layout)
    return layout


def resolve_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text())
    config['policy'] = validate_policy(config.get('policy', {}))
    if not config.get('scenario_id') or config['scenario_id'] in ('UNKNOWN', 'REQUIRED'):
        raise ValueError("Register a flood scenario_id; an SRI label does not automatically imply a return period")
    if not config.get('groundwater_scenario_id'):
        raise ValueError("Register a groundwater_scenario_id (it can be explicitly unknown, keeping gates conditional)")
    if not config.get('run_id') or not config.get('area_label'):
        raise ValueError("run_id and area_label are required")
    intervention_need(0, config['flood_threshold_m'])
    config['designs'] = config.get('designs', list(DESIGNS))
    if not config['designs'] or any(d not in DESIGNS for d in config['designs']):
        raise ValueError("designs must be a nonempty list of catalogue design IDs")
    for key in ('flood', 'study_area', 'ownership'):
        if config.get(key) and config[key].get('path'):
            config[key]['path'] = str((path.parent / config[key]['path']).resolve())
    for spec in config.get('evidence', []) + config.get('raster_evidence', []) + config.get('distance_evidence', []):
        spec['path'] = str((path.parent / spec['path']).resolve())
    muriel = config.get('muriel') or {}
    for spec in muriel.get('receptors', []) + [muriel[k] for k in ('municipal_land', 'roads', 'usable_space', 'routes') if muriel.get(k)]:
        spec['path'] = str((path.parent / spec['path']).resolve())
    config['output_dir'] = str((path.parent / config['output_dir']).resolve())
    return config


def run(config_path, export_maps=True):
    config = resolve_config(config_path)
    out = Path(config['output_dir'])
    if out.exists():
        raise ValueError(f"Output directory already exists: {out}. Use a new run_id/output path to preserve earlier runs.")
    crs = QgsCoordinateReferenceSystem(config.get('crs', 'EPSG:25832'))
    if not crs.isValid() or crs.isGeographic() or crs.mapUnits() != Qgis.DistanceUnit.Meters:
        raise ValueError("Use a valid projected CRS in metres")
    # A private project protects an existing QGIS GUI session and its unsaved
    # project from being cleared when the workflow runs through Processing.
    project = QgsProject()
    project.setCrs(crs)
    units, aoi, grid = read_units(config, crs)
    config['analysis_grid_description'] = (' × '.join(f'{v:g}' for v in grid['pixel_size_m']) + ' m; source grid retained') if grid['type'] == 'raster_cells' else 'Input polygon partition; source resolution applies'
    for spec in config.get('evidence', []):
        features = load_vector(spec, crs)
        fields = spec.get('fields') or {key: key for key in features[0][1] if key != spec.get('id_field', 'unit_id')}
        if set(fields) & {'unit_id', 'area_m2', 'flood_depth_m'}:
            raise ValueError('Evidence overlays may not overwrite analysis IDs, measured area or flood depth')
        if spec.get('join', 'id') == 'id':
            records = {}
            for _, a in features:
                uid = str(a.get(spec.get('id_field', 'unit_id')))
                if uid in records:
                    raise ValueError(f"Duplicate evidence unit ID {uid}")
                records[uid] = a
            for u in units:
                a = records.get(u['attrs']['unit_id'], {})
                u['attrs'].update({target: a.get(origin) for target, origin in fields.items()})
        elif spec['join'] == 'spatial':
            idx, records = indexed(features)
            for u in units:
                u['attrs'].update(join_evidence(u['geometry'], idx, records, fields))
        else:
            raise ValueError("Evidence join must be id or spatial")
    derived_evidence(config, units, grid, crs)
    if config.get('ownership'):
        spec = config['ownership']
        idx, records = indexed(load_vector(spec, crs))
        for u in units:
            u['attrs'].update(ownership(u['geometry'], idx, records, spec.get('class_field', 'owner_class'), spec['mapping']))
    else:
        for u in units:
            u['attrs'].update(owner_class='unknown', municipal_fraction=0., private_fraction=0., other_public_fraction=0., unknown_fraction=1., ownership_overlap_m2=0.)

    # Compute all checks before writing results; input and reference errors do not
    # leave a misleading completed output directory.
    evaluations, audit, nbs, gw_records, need_records, owner_records = {}, [], [], [], [], []
    for u in units:
        a, geom = u['attrs'], u['geometry']
        uid = a['unit_id']
        base = {k: a.get(k) for k in ('unit_id', 'flood_depth_m', 'area_m2', 'owner_class', 'municipal_fraction', 'private_fraction', 'other_public_fraction', 'unknown_fraction', 'ownership_overlap_m2')}
        base.update(scenario_id=config['scenario_id'], groundwater_scenario_id=config['groundwater_scenario_id'], run_id=config['run_id'], is_demo=int(config.get('demo', False)))
        need = intervention_need(a.get('flood_depth_m'), config['flood_threshold_m'])
        need_records.append(({**base, 'status': need, 'threshold_m': config['flood_threshold_m'], 'explanation': f"Depth {a.get('flood_depth_m')} m compared with ≥{config['flood_threshold_m']} m. UNKNOWN preserves NoData. {SOURCES['USER_DEPTH']['citation']}. Below-threshold source-control locations remain eligible for separate investigation."}, geom))
        owner_records.append(({**base, 'status': base['owner_class'], 'explanation': 'Ownership overlay uses polygon intersection area, not centroids. Missing coverage is unknown; overlapping parcels are flagged as conflict. Private ownership is a delivery category, not automatic technical failure. See input_provenance for the ownership source.'}, geom))
        gw_rows = groundwater(a, config['policy'], vertical_datum=config.get('vertical_datum'), groundwater_scenario_id=config['groundwater_scenario_id'])
        gw_records.append(({**base, **summary(gw_rows)}, geom))
        for d in gw_rows:
            audit.append({'unit_id': uid, 'design': 'PRELIMINARY_GROUNDWATER', 'scenario_id': config['scenario_id'], **d.record()})
        for design in config['designs']:
            rows = evaluate_design(a, design, config['policy'], config.get('vertical_datum'), config['groundwater_scenario_id'])
            evaluations[(uid, design)] = rows
            nbs.append(({**base, 'design': design, 'design_label': DESIGNS[design][0], 'family': DESIGNS[design][1], 'pathway': 'infiltration' if DESIGNS[design][2] else 'no_deliberate_infiltration', 'need_local': need, **summary(rows)}, geom))
            for d in rows:
                audit.append({'unit_id': uid, 'design': design, 'scenario_id': config['scenario_id'], **d.record()})

    unit_map = {u['attrs']['unit_id']: u['attrs'] for u in units}
    geom_map = {u['attrs']['unit_id']: u['geometry'] for u in units}
    combos = []
    combo_ids = set()
    for combo in config.get('combinations', []):
        if not combo.get('id') or combo['id'] in combo_ids:
            raise ValueError("Combinations require unique nonempty IDs")
        combo_ids.add(combo['id'])
        rows = evaluate_combination(combo, evaluations, unit_map)
        geoms = [geom_map[str(m['unit_id'])] for m in combo.get('modules', [])]
        if not geoms:
            raise ValueError("Combination requires known spatial members")
        geom = QgsGeometry.unaryUnion(geoms)
        combos.append(({'combination_id': combo['id'], 'scenario_id': config['scenario_id'], 'run_id': config['run_id'],
                        'members': json.dumps(combo['modules']), 'is_demo': int(config.get('demo', False)), **summary(rows)}, geom))
        for d in rows:
            audit.append({'unit_id': combo['id'], 'design': 'COMBINATION', 'scenario_id': config['scenario_id'], **d.record()})

    muriel = None
    if (config.get('muriel') or {}).get('enabled') is True:
        from .muriel import screen
        muriel = screen(units, aoi, crs, config, gw_records)
        audit.extend(muriel['audit'])
    out.mkdir(parents=True)
    # Build under a staging filename so the complete analytical schema exists
    # before any consumer opens the final deliverable.
    gpkg = out / '_stage1_build.gpkg'
    layers = [('intervention_need', need_records), ('groundwater_screen', gw_records), ('nbs_opportunities', nbs), ('ownership', owner_records)]
    if combos:
        layers.append(('combinations', combos))
    if muriel:
        for name, key in [('muriel_source_mask', 'source_mask'), ('muriel_hotspots', 'hotspots'), ('muriel_priority', 'priority'), ('muriel_destinations', 'destinations'), ('muriel_connections', 'connections'), ('muriel_context', 'context')]:
            if muriel[key]:
                layers.append((name, muriel[key]))
    for i, (name, records) in enumerate(layers):
        write_layer(gpkg, memory_layer(name, records, crs, geometry_type='MultiLineString' if name == 'muriel_connections' else None), name, first=i == 0)
    provenance = []
    specs = [('flood', config['flood']), ('study_area', config['study_area'])] + [(key, s) for key in ('evidence', 'raster_evidence', 'distance_evidence') for s in config.get(key, [])]
    if config.get('ownership'):
        specs.append(('ownership', config['ownership']))
    if muriel:
        specs.extend(muriel['sources'])
    for role, spec in specs:
        provenance.append({'role': role, 'path': spec['path'], 'layer': spec.get('layer'), 'sha256': checksum(spec['path']),
                           'metadata': json.dumps(spec.get('metadata', {}), ensure_ascii=False)})
    with sqlite3.connect(gpkg) as db:
        add_attribute_table(db, 'decision_audit', audit)
        db.execute('CREATE INDEX audit_lookup ON decision_audit(unit_id, design, scenario_id)')
        add_attribute_table(db, 'source_registry', [{'source_id': k, **v} for k, v in SOURCES.items()])
        add_attribute_table(db, 'input_provenance', provenance)
    db.close()
    final_gpkg = out / 'stage1.gpkg'
    gpkg.replace(final_gpkg)
    gpkg = final_gpkg
    csv_write(out / 'decision_audit.csv', audit)
    csv_write(out / 'source_registry.csv', [{'source_id': k, **v} for k, v in SOURCES.items()])
    csv_write(out / 'candidate_register.csv', [{k: v for k, v in a.items() if k != 'explanation'} for a, _ in nbs])
    csv_write(out / 'combinations_register.csv', [a for a, _ in combos])
    csv_write(out / 'evidence_snapshot.csv', [u['attrs'] for u in units])
    if muriel:
        for key in ('priority', 'destinations', 'connections'):
            csv_write(out / f'muriel_{key}.csv', [a for a, _ in muriel[key]])
        (out / 'muriel_summary.json').write_text(json.dumps(muriel['summary'], indent=2))
    manifest = {'software': {'qgis': Qgis.QGIS_VERSION, 'gdal': gdal.VersionInfo(), 'workflow': '0.2.0'},
                'created_at_utc': datetime.now(timezone.utc).isoformat(), 'run_id': config['run_id'],
                'demo': config.get('demo', False), 'unit_count': len(units), 'grid': grid, 'inputs': provenance,
                'config_sha256': checksum(config_path),
                'code_sha256': {p.name: checksum(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
                'limitations': [
                    'Spatial screening only; no hydraulic effects, lifecycle cost, or Pareto front calculated.',
                    'Current primary-source legal / technical verification requires local review.',
                    'Preliminary groundwater screen remains conditional without specific module geometry.',
                    'Groundwater is an admissibility gate, not a simulated aquifer response.',
                    'MURIEL executed as a local planning screen; proximity connectors are not hydraulic flow paths.' if muriel else 'MURIEL is disabled for this run; enable the muriel configuration to execute it.',
                    'Ownership does not establish land rights; private land is not automatically rejected.',
                ]}
    manifest['muriel'] = muriel['summary'] if muriel else {'enabled': False}
    if config.get('demo'):
        manifest['limitations'].insert(0, 'ALL INPUTS, EVIDENCE AND AUTHORITY DECISIONS ARE SYNTHETIC. NOT KÖLN-KALK FINDINGS.')
    (out / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    (out / 'resolved_config.json').write_text(json.dumps(config, indent=2, ensure_ascii=False))

    maps = [
        ('intervention_need', '01 · Flood intervention need', None, 'Depth ≥10 cm is the initial\nuser-defined intervention screen.\nThe threshold is configurable.\n\nNoData is unknown, never dry.\nUpstream source-control options\nare not removed by this map.'),
        ('groundwater_screen', '02 · Preliminary infiltration pathway', None, 'This is a pathway-risk screen.\nKnown prohibitions remain FAIL.\nMissing evidence is CONDITIONAL.\n\nFinal separation needs a specific\nmodule base and a design\ngroundwater state on one datum.'),
        ('ownership', '03 · Land ownership and delivery', None, 'Ownership is intersected by area.\nMixed units retain area shares.\nMissing coverage stays unknown.\nOverlapping parcels are flagged.\n\nPrivate land may be feasible\nwith the necessary agreement.'),
    ]
    # Dynamic threshold text, including after a sensitivity rerun.
    maps[0] = (*maps[0][:3], maps[0][3].replace('≥10 cm', f"≥{config['flood_threshold_m']*100:g} cm"))
    for design in config['designs']:
        maps.append(('nbs_opportunities', DESIGNS[design][0], design,
                     'All applicable gates are evaluated.\nFAIL takes precedence over\nconditional and admissible.\n\nEach feature stores the reasons,\nrule IDs, references, evidence\nand required closure actions.\n\nAdmissible means screening only.'))
    if combos:
        maps.append(('combinations', 'Combined systems · compatibility', None,
                     'Each declared combination tests\nits members, footprint and source\nallocations, routing, shared\ncapacity, outlet and delivery.\n\nNo hydraulic benefit is added.\nEach combination has its own layer\nto avoid hiding overlapping sites.'))

    muriel_map_fields = {'muriel_source_mask': 'mask_class', 'muriel_hotspots': 'hotspot_class', 'muriel_priority': 'planning_class', 'muriel_destinations': 'status', 'muriel_connections': 'line_kind'}
    muriel_context = None
    if muriel and muriel['context']:
        muriel_context = styled_layer(gpkg, 'muriel_context', 'MURIEL · source context', field='context_type')
        project.addMapLayer(muriel_context)
    if muriel:
        from .engine import muriel_settings
        p = muriel_settings(config['muriel'].get('thresholds'))
        notes = (f'Area >{p["min_area_m2"]:g} m²; max depth\n>{p["min_max_depth_m"]:g} m. Receptor <{p["receptor_distance_m"]:g} m;\nmunicipal non-road land <{p["municipal_distance_m"]:g} m;\nusable destination ≤{p["destination_distance_m"]:g} m.\nProtect overlap ≥{p["protect_overlap_fraction"]*100:g}%.\n\nGrey: buildings / receptors.\nPale blue: flood footprint.\nBeige: roads. Pale green: city land.\n\nSchwerdorf (2022); thesis §§4.4.2,\n5.5.3. Reasons and evidence are\nstored with every feature.')
        notes += '\n\nFootprint: ' + p['footprint_mode']
        for table, title in [('muriel_source_mask', 'MURIEL · registered flood-depth mask'), ('muriel_hotspots', 'MURIEL · flood hotspot screen'), ('muriel_priority', 'MURIEL · protect, investigate or adapt'), ('muriel_destinations', 'MURIEL · usable municipal destinations'), ('muriel_connections', 'MURIEL · routing evidence and gaps')]:
            if any(name == table for name, _ in layers):
                maps.append((table, title, None, notes + ('\n\nDashed lines show proximity or\nincomplete evidence; no flow proof.' if table == 'muriel_connections' else '')))

    pages, exported, map_layers = [], [], []
    for table, title, design, notes in maps:
        # Overlapping portfolios must never conceal one another on one map.
        combo_subsets = [a['combination_id'] for a, _ in combos] if table == 'combinations' else [None]
        for combo_id in combo_subsets:
            subset = f'"design" = \'{design}\'' if design else None
            if combo_id:
                subset = '"combination_id" = \'' + combo_id.replace("'", "''") + "'"
            name = title + (' · ' + combo_id if combo_id else '')
            layer = styled_layer(gpkg, table, name, field=muriel_map_fields.get(table, 'status'), subset=subset)
            project.addMapLayer(layer)
            map_layers.append(layer)
            if export_maps:
                layout = make_layout(project, layer, name, config, notes, aoi.boundingBox(), len(pages) + 1,
                                     context_layers=[muriel_context] if table.startswith('muriel_') and muriel_context else None)
                pages.append(layout)
                fname = f'{len(pages):02d}_' + re.sub(r'[^A-Za-z0-9_-]', '_', combo_id or design or table)
                exporter = QgsLayoutExporter(layout)
                png = out / (fname + '.png')
                # These are publication sheets, not analytical rasters. Saving
                # the rendered QImage avoids QGIS trying to reopen PNG in GDAL
                # update mode to write unsupported georeferencing metadata.
                rendered = exporter.renderPageToImage(0, dpi=140)
                if rendered.isNull() or not rendered.save(str(png), 'PNG'):
                    raise RuntimeError(f"Map export failed: {png}")
                exported.append((name, png.name))
    for table in ('decision_audit', 'source_registry', 'input_provenance'):
        layer = QgsVectorLayer(f'{gpkg}|layername={table}|option:NOLOCK=NO', table, 'ogr')
        if not layer.isValid():
            raise RuntimeError(f"Audit table did not reopen: {table}")
        project.addMapLayer(layer)
    # Open on one clear map, with named themes for switching without stacking
    # several differently classified copies of the same grid.
    from qgis.core import QgsLayerTreeModel, QgsMapThemeCollection
    tree = project.layerTreeRoot()
    model = QgsLayerTreeModel(tree)
    for visible in map_layers:
        for layer in map_layers:
            tree.findLayer(layer.id()).setItemVisibilityChecked(layer == visible)
        if muriel_context:
            tree.findLayer(muriel_context.id()).setItemVisibilityChecked(visible.name().startswith('MURIEL'))
        theme = QgsMapThemeCollection.createThemeFromCurrentState(tree, model)
        project.mapThemeCollection().insert(visible.name(), theme)
    for layer in map_layers:
        tree.findLayer(layer.id()).setItemVisibilityChecked(layer == map_layers[0])
    if muriel_context:
        tree.findLayer(muriel_context.id()).setItemVisibilityChecked(False)
    project.viewSettings().setDefaultViewExtent(__import__('qgis.core', fromlist=['QgsReferencedRectangle']).QgsReferencedRectangle(aoi.boundingBox(), crs))
    project.setFilePathStorage(Qgis.FilePathType.Relative)
    project.setFileName(str(out / 'stage1.qgz'))
    if not project.write():
        raise RuntimeError('Could not save QGIS project')
    if pages:
        # Export one multi-page QGIS report via individual PDFs + trusted installed
        # PDF tooling; keep PDFs if no merger is available.
        import subprocess, shutil
        pdfs = []
        for i, layout in enumerate(pages):
            target = out / f'_sheet_{i+1:02d}.pdf'
            settings = QgsLayoutExporter.PdfExportSettings()
            settings.dpi = 180
            if QgsLayoutExporter(layout).exportToPdf(str(target), settings) != QgsLayoutExporter.Success:
                raise RuntimeError(f'PDF export failed: {target}')
            pdfs.append(target)
        if shutil.which('pdfunite'):
            subprocess.run(['pdfunite', *map(str, pdfs), str(out / 'stage1_atlas.pdf')], check=True)
            muriel_pdfs = [p for p, layout in zip(pdfs, pages) if 'MURIEL ·' in layout.name()]
            if muriel_pdfs:
                subprocess.run(['pdfunite', *map(str, muriel_pdfs), str(out / 'muriel_atlas.pdf')], check=True)
            for p in pdfs:
                p.unlink()
    create_report(out, config, layers, manifest, exported)
    return out


def create_report(out, config, layers, manifest, exported):
    counts = {}
    for name, records in layers:
        if name == 'nbs_opportunities':
            for design in config['designs']:
                selected = [a for a, _ in records if a['design'] == design]
                counts[design] = {s: sum(a['status'] == s for a in selected) for s in ('ADMISSIBLE', 'CONDITIONAL', 'FAIL')}
        else:
            field = 'planning_class' if name == 'muriel_priority' else 'hotspot_class' if name == 'muriel_hotspots' else 'context_type' if name == 'muriel_context' else 'status'
            counts[name] = {s: sum(a[field] == s for a, _ in records) for s in sorted({a[field] for a, _ in records})}
    (out / 'summary.json').write_text(json.dumps(counts, indent=2))
    banner = 'SYNTHETIC DEMONSTRATION — NOT KÖLN-KALK RESULTS' if config.get('demo') else 'SPATIAL SCREENING — NOT CONSTRUCTION APPROVAL'
    figures = ''.join(f'<figure><a href="{html.escape(file)}"><img src="{html.escape(file)}" alt="{html.escape(name)}"></a><figcaption>{html.escape(name)}</figcaption></figure>' for name, file in exported)
    rows = ''.join(f'<tr><td>{html.escape(k)}</td><td>{html.escape(json.dumps(v))}</td></tr>' for k, v in counts.items())
    limitations = ''.join('<li>' + html.escape(s) + '</li>' for s in manifest['limitations'])
    pdf_links = '<a href="stage1_atlas.pdf">PDF atlas</a>' if (out / 'stage1_atlas.pdf').exists() else ' '.join(f'<a href="{p.name}">PDF sheet {i+1}</a>' for i, p in enumerate(sorted(out.glob('_sheet_*.pdf'))))
    if not pdf_links:
        pdf_links = 'Map-file export was disabled for this run'
    if (out / 'muriel_atlas.pdf').exists():
        pdf_links += ' · <a href="muriel_atlas.pdf">MURIEL atlas</a>'
    muriel_report = ''
    if manifest.get('muriel', {}).get('enabled'):
        m = manifest['muriel']
        if (out / 'muriel_priority.csv').exists():
            pdf_links += ' · <a href="muriel_priority.csv">MURIEL decision register</a>'
        muriel_report = (f'<h2>MURIEL planning screen</h2><p>Observed footprints: {m["footprint_count"]}; '
                         f'eligible destinations: {m["destination_count"]}; unknown source units: {m["unknown_source_unit_count"]}. '
                         f'Footprint mode: <code>{html.escape(m["thresholds"]["footprint_mode"])}</code>. '
                         '<a href="muriel_summary.json">Registered criteria and counts</a>. '
                         'Zero observed hotspots with missing source data does not establish absence of hazard.</p>')
    doc = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Stage 1 NbS opportunity atlas</title>
<style>body{{font:16px/1.55 system-ui;max-width:1180px;margin:30px auto;padding:0 24px;color:#243e4a;background:#f6f8fa}}h1{{font-size:36px}}.banner{{background:#ffe3d9;padding:16px;font-weight:700}}.maps{{display:grid;grid-template-columns:repeat(auto-fit,minmax(450px,1fr));gap:24px}}figure{{margin:0;background:white;padding:10px}}img{{width:100%}}table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;border-bottom:1px solid #ccd5dc;padding:9px}}code{{background:#e9edf0}}a{{color:#116963}}</style>
<p class="banner">{banner}</p><h1>Stage 1 · NbS opportunity atlas</h1><p>{html.escape(config['area_label'])} / {html.escape(config['scenario_id'])}</p>
<p>Open <a href="stage1.qgz">stage1.qgz</a> in QGIS. Select an NbS layer and use <b>Identify Features</b> to inspect <code>explanation</code>, rule IDs, evidence and source links. The <code>decision_audit</code> table holds one row per rule.</p>
<p>{pdf_links} · <a href="candidate_register.csv">Candidate register</a> · <a href="decision_audit.csv">Decision audit</a> · <a href="source_registry.csv">Sources</a> · <a href="run_manifest.json">Provenance manifest</a></p>
<h2>Interpretation and outstanding evidence</h2><ul>{limitations}</ul>
{muriel_report}
<h2>Class counts</h2><p>Counts are analysis units per design, not independent sites or delivered projects. Geometry and effect need separate assessment.</p><table><tr><th>Layer / design</th><th>Counts</th></tr>{rows}</table>
<h2>Map sheets</h2><div class="maps">{figures}</div></html>'''
    (out / 'report.html').write_text(doc, encoding='utf-8')
