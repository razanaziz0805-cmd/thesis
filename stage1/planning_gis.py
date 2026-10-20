"""Small-input Phase C workflow: flood action areas and conditional concepts."""
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess

from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsGeometry, QgsLayerTreeModel,
                       QgsLayoutExporter, QgsMapThemeCollection, QgsProject, QgsReferencedRectangle,
                       QgsVectorLayer)
from osgeo import gdal

from . import __version__
from .catalogue import SOURCES
from .configuration import input_specs, resolve_config
from .engine import Decision, groundwater, intervention_need
from .gis import (PALETTE, add_attribute_table, attach_evidence, checksum, csv_write, indexed,
                  join_evidence, load_vector, make_layout, memory_layer, ownership, read_units,
                  styled_layer, summary, write_layer)
from .muriel import polygon_parts, union
from .planning import FAMILIES, delivery_action, opportunity


def mapped_features(spec, crs, target, control):
    """Source categories are explicitly mapped; unlisted values remain unknown."""
    result = []
    for geom, attrs in load_vector(spec, crs, control=control):
        if spec['class_field'] not in attrs:
            raise ValueError('Category field is absent: ' + spec['class_field'])
        result.append((geom, {target: spec['mapping'].get(str(attrs[spec['class_field']]), 'unknown')}))
    return result


def action_areas(units, aoi, threshold_m, control=None):
    """Edge-connected need mask; no minimum-area cut-off or invented flow path."""
    wet = [u for u in units if intervention_need(u['attrs'].get('flood_depth_m'), threshold_m) == 'YES']
    if not wet:
        return [], {}
    idx, records = indexed([(u['geometry'], u['attrs']) for u in wet])
    missing = union([aoi.difference(union(u['geometry'] for u in units)),
                     *(u['geometry'] for u in units if u['attrs'].get('flood_depth_m') is None)])
    boundary = QgsGeometry(aoi.constGet().boundary())
    areas, membership = [], {}
    for geom in polygon_parts(union(u['geometry'] for u in wet)):
        if control:
            control.check()
        members = [records[i][1] for i in idx.intersects(geom.boundingBox())
                   if geom.intersection(records[i][0]).area() > 1e-8]
        canonical = QgsGeometry(geom); canonical.normalize()
        ident = 'ACT_' + hashlib.sha256(bytes(canonical.asWkb())).hexdigest()[:12]
        incomplete = geom.distance(boundary) < 1e-7 or (not missing.isEmpty() and geom.distance(missing) < 1e-7)
        attributes = dict(action_id=ident, area_m2=geom.area(), max_depth_m=max(m['flood_depth_m'] for m in members),
                          member_count=len(members), extent_incomplete=int(incomplete),
                          status='CONDITIONAL', action_class='REVIEW_FLOOD',
                          reason_code='PL_FLOOD_ACTION', reference='User-defined need threshold; thesis §§5.1, 5.5.1',
                          explanation=f'Connected mapped area with depth ≥{threshold_m*100:g} cm. '
                          'This is a planning discussion area, not a designed module, catchment or verified storage volume. '
                          + ('Extent touches the study edge or unknown coverage and may continue outside the observed footprint. ' if incomplete else '')
                          + 'Reference: thesis §§5.1 and 5.5.1; user-defined flood-depth screen.')
        areas.append((attributes, geom))
        for member in members:
            membership.setdefault(member['unit_id'], []).append(ident)
    # This is a transparent browsing order, not an objective function or risk score.
    areas.sort(key=lambda r: (-r[0]['max_depth_m'], -r[0]['area_m2'], r[0]['action_id']))
    for i, (attributes, _) in enumerate(areas, 1):
        attributes['action_label'] = f'A{i:03d}'
        attributes['browse_order'] = i
    return areas, membership


def run_planning(config_path, export_maps, control, out):
    config = resolve_config(config_path)
    crs = QgsCoordinateReferenceSystem(config.get('crs', 'EPSG:25832'))
    if not crs.isValid() or crs.isGeographic() or crs.mapUnits() != Qgis.DistanceUnit.Meters:
        raise ValueError('Use a projected processing CRS in metres.')
    control.phase(3, 'Reading flood depths and boundary')
    units, aoi, grid = read_units(config, crs, control)
    uncovered = aoi.difference(union(u['geometry'] for u in units))
    if uncovered.area() > 1e-8:
        units.append({'geometry':uncovered, 'attrs':dict(unit_id='UNMAPPED_FLOOD_COVERAGE', flood_depth_m=None, area_m2=uncovered.area())})
    config['analysis_grid_description'] = (' × '.join(f'{n:g}' for n in grid['pixel_size_m']) + ' m; source grid retained') if grid['type'] == 'raster_cells' else 'Input polygon partition'
    control.phase(15, 'Adding optional planning context')
    attach_evidence(config, units, grid, crs, control)
    planning = config.get('planning') or {}
    surfaces = planning.get('surfaces')
    if surfaces:
        idx, rec = indexed(mapped_features(surfaces, crs, 'land_type', control))
        for i, unit in enumerate(units):
            if i % 128 == 0:
                control.check()
            unit['attrs'].update(join_evidence(unit['geometry'], idx, rec, {'land_type': 'land_type'}))
    heat = mapped_features(planning['heat'], crs, 'heat_class', control) if planning.get('heat') else []
    heat_priority = union(g for g, a in heat if a['heat_class'] == 'priority')
    heat_other = union(g for g, a in heat if a['heat_class'] == 'other')
    heat_conflict = heat_priority.intersection(heat_other) if not heat_priority.isEmpty() and not heat_other.isEmpty() else QgsGeometry()
    heat_conflict = union([heat_conflict, *(g for g,a in heat if a['heat_class'] == 'unknown')])
    # Contradictory category evidence contributes to unknown, never a priority pass.
    heat_priority = heat_priority.difference(heat_conflict) if not heat_conflict.isEmpty() else heat_priority
    heat_other = heat_other.difference(heat_conflict) if not heat_conflict.isEmpty() else heat_other
    heat_known = union([heat_priority, heat_other])
    restriction_spec = planning.get('restrictions')
    restrictions = mapped_features(restriction_spec, crs, 'restriction', control) if restriction_spec else []
    excluded = union(g for g,a in restrictions if a['restriction'] == 'infiltration_excluded')
    owner_spec = config.get('ownership')
    owner_index, owner_records = indexed(load_vector(owner_spec, crs, control=control)) if owner_spec else indexed([])
    control.phase(25, 'Building connected flood action areas')
    actions, membership = action_areas(units, aoi, config['flood_threshold_m'], control)
    need_records, gw_records, concepts, owner_layer, audit, heat_records = [], [], [], [], [], []
    for i, unit in enumerate(units):
        if i % 128 == 0:
            control.update(30 + 20*i/len(units), f'Screening planning unit {i+1:,} / {len(units):,}')
        a, geom = unit['attrs'], unit['geometry']
        base = {key: a.get(key) for key in ('unit_id', 'flood_depth_m', 'area_m2', 'owner_class', 'municipal_fraction', 'private_fraction', 'other_public_fraction', 'unknown_fraction', 'ownership_overlap_m2')}
        base.update(scenario_id=config['scenario_id'], run_id=config['run_id'], is_demo=int(config.get('demo', False)),
                    action_ids='; '.join(membership.get(a['unit_id'], [])))
        need = intervention_need(a.get('flood_depth_m'), config['flood_threshold_m'])
        need_records.append(({**base, 'status': need, 'threshold_m': config['flood_threshold_m'],
                              'explanation': f'Depth {a.get("flood_depth_m")} m compared with ≥{config["flood_threshold_m"]} m. '
                              'Unknown values remain unknown. Source-control opportunities below this local threshold are retained. '
                              'Rule: user-defined depth screen; flood evidence: checksummed input_provenance.'}, geom))
        gw = groundwater(a, config['policy'], vertical_datum=config.get('vertical_datum'), groundwater_scenario_id=config['groundwater_scenario_id'])
        if not excluded.isEmpty() and geom.intersection(excluded).area() > 1e-8:
            gw.append(Decision('PL_KNOWN_INFILTRATION_EXCLUSION', 'FAIL',
                               'The unit intersects a source class explicitly registered as a known infiltration exclusion.',
                               str(restriction_spec['mapping']), 'No intersecting known prohibition for the infiltration pathway',
                               'THESIS', 'planning.restrictions; see checksummed input_provenance and source category mapping',
                               'Evidence owner / competent water authority',
                               'Retain infiltration FAIL; investigate a separate lined / controlled-release pathway and its own safety gates.'))
        gs = summary(gw)
        gw_records.append(({**base, **gs}, geom))
        for decision in gw:
            audit.append(dict(unit_id=a['unit_id'], design='PRELIMINARY_GROUNDWATER', scenario_id=config['scenario_id'], **decision.record()))
        owner_layer.append(({**base, 'status': a['owner_class'], 'next_action': delivery_action(a['owner_class']),
                             'explanation': 'Exact ownership area shares; unknown coverage and overlaps are explicit. '
                             'Private land remains a partnership route. Land use and public purpose do not establish legal ownership. '
                             'Source: ownership input_provenance; thesis §§5.4.1, 5.5.4.'}, geom))
        for family in FAMILIES:
            concepts.append(({**base, **opportunity(a, family, gs['status'], config['flood_threshold_m'])}, geom))
    control.phase(52, 'Preparing delivery shortlist and optional MURIEL screen')
    options_by_action = {}
    for attributes, _ in concepts:
        if attributes['opportunity_class'] == 'INVESTIGATE':
            for action_id in membership.get(attributes['unit_id'], []):
                options_by_action.setdefault(action_id, set()).add(attributes['family_label'])
    for a, geom in actions:
        own = ownership(geom, owner_index, owner_records, owner_spec.get('class_field', 'owner_class'), owner_spec['mapping']) if owner_spec else dict(owner_class='unknown', municipal_fraction=0., private_fraction=0., other_public_fraction=0., unknown_fraction=1., ownership_overlap_m2=0.)
        a.update(own)
        a.update(scenario_id=config['scenario_id'], run_id=config['run_id'], is_demo=int(config.get('demo', False)),
                 delivery_action=delivery_action(own['owner_class']), next_action='Inspect receptors and source → inlet → storage → outlet / safe overflow; ' + delivery_action(own['owner_class']))
        a['investigation_families'] = '; '.join(sorted(options_by_action.get(a['action_id'], []))) or 'Surface evidence unresolved; verify typology before selection.'
        a['concept_note'] = 'Families are investigation alternatives; shared footprint, capacity and flow links have not been verified for a combination.'
        a['heat_priority_fraction'] = geom.intersection(heat_priority).area()/geom.area() if not heat_priority.isEmpty() else (0. if heat else None)
        a['heat_unknown_fraction'] = 1 - geom.intersection(heat_known).area()/geom.area() if not heat_known.isEmpty() else 1.
        a['heat_context'] = 'Documented heat-priority overlap; no cooling magnitude calculated.' if heat else 'No heat evidence supplied.'
        a['explanation'] += '\n' + a['delivery_action'] + '\n' + a['heat_context']
        a['explanation'] += '\nPossible investigations: ' + a['investigation_families'] + '\n' + a['concept_note']
    for category, geom in [('HEAT_PRIORITY', heat_priority), ('HEAT_OTHER', heat_other), ('HEAT_UNKNOWN', aoi.difference(heat_known))]:
        if not geom.isEmpty():
            cut = geom.intersection(aoi)
            if cut.area() > 1e-8:
                heat_records.append((dict(status=category, explanation='Observed heat context, explicitly mapped source categories; unlisted, conflicting and uncovered areas remain unknown. '
                                         'No NbS temperature reduction is calculated. Thesis §§4.2, 5.7.4; source: planning.heat in input_provenance.'), cut))
    muriel = None
    if (config.get('muriel') or {}).get('enabled') is True:
        from .muriel import screen
        muriel = screen(units, aoi, crs, config, gw_records, control)
        audit.extend(muriel['audit'])
    layers = [('intervention_need', need_records), ('groundwater_screen', gw_records),
              ('planning_opportunities', concepts), ('ownership', owner_layer)]
    if actions:
        layers.append(('planning_action_areas', actions))
    if heat:
        layers.append(('heat_context', heat_records))
    if muriel:
        for name, key in [('muriel_source_mask', 'source_mask'), ('muriel_hotspots', 'hotspots'), ('muriel_priority', 'priority'), ('muriel_destinations', 'destinations'), ('muriel_connections', 'connections'), ('muriel_context', 'context')]:
            if muriel[key]:
                layers.append((name, muriel[key]))
    control.phase(60, 'Writing planning GeoPackage and registers')
    gpkg = out/'stage1.gpkg'
    for i, (name, records) in enumerate(layers):
        control.check()
        write_layer(gpkg, memory_layer(name, records, crs, geometry_type='MultiLineString' if name == 'muriel_connections' else None), name, first=i == 0)
    provenance, hashes = [], {}
    for role, spec in input_specs(config):
        if spec['path'] not in hashes:
            hashes[spec['path']] = checksum(spec['path'])
        provenance.append(dict(role=role, path=spec['path'], layer=spec.get('layer'), sha256=hashes[spec['path']], metadata=json.dumps(spec.get('metadata', {}), ensure_ascii=False)))
    with sqlite3.connect(gpkg) as db:
        for name, rows in [('decision_audit', audit), ('source_registry', [dict(source_id=k, **v) for k,v in SOURCES.items()]), ('input_provenance', provenance)]:
            add_attribute_table(db, name, rows)
    db.close()
    csv_write(out/'decision_audit.csv', audit)
    csv_write(out/'source_registry.csv', [dict(source_id=k, **v) for k,v in SOURCES.items()])
    csv_write(out/'planning_options.csv', [a for a,_ in concepts])
    csv_write(out/'planning_shortlist.csv', [a for a,_ in actions])
    csv_write(out/'action_membership.csv', [dict(unit_id=uid, action_id=aid) for uid, ids in membership.items() for aid in ids])
    for filename, fields in [('planning_shortlist.csv', ['action_id','action_label','area_m2','max_depth_m','status','next_action']),
                             ('action_membership.csv', ['unit_id','action_id'])]:
        if not (out/filename).exists():
            with (out/filename).open('w', newline='', encoding='utf-8') as file:
                csv.writer(file).writerow(fields)
    csv_write(out/'evidence_snapshot.csv', [u['attrs'] for u in units])
    if muriel:
        for key in ('priority', 'destinations', 'connections'):
            csv_write(out/f'muriel_{key}.csv', [a for a,_ in muriel[key]])
        (out/'muriel_summary.json').write_text(json.dumps(muriel['summary'], indent=2))
    family_counts = {key: dict(Counter(a['opportunity_class'] for a,_ in concepts if a['family'] == key)) for key in FAMILIES}
    stats = dict(study_area_m2=aoi.area(), flood_need_area_m2=sum(a['area_m2'] for a,_ in need_records if a['status'] == 'YES'),
                 flood_unknown_area_m2=sum(a['area_m2'] for a,_ in need_records if a['status'] == 'UNKNOWN') + max(0., aoi.area()-sum(a['area_m2'] for a,_ in need_records)),
                 action_area_count=len(actions), family_counts=family_counts,
                 browsing_order='Maximum mapped depth descending, then mapped area descending; no composite risk score.',
                 concepts_are_conditional=True)
    manifest = dict(software=dict(qgis=Qgis.QGIS_VERSION, gdal=gdal.VersionInfo(), workflow=__version__), mode='planning',
                    created_at_utc=datetime.now(timezone.utc).isoformat(), run_id=config['run_id'], demo=config.get('demo', False),
                    unit_count=len(units), grid=grid, inputs=provenance, config_sha256=checksum(config_path),
                    code_sha256={p.name:checksum(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
                    planning=stats, preparation=config.get('preparation') or {'enabled':False},
                    muriel=muriel['summary'] if muriel else {'enabled':False},
                    limitations=['Phase C planning opportunities only; every retained concept is CONDITIONAL. No final design PASS.',
                                 'Known infiltration prohibitions are retained; lined alternatives still require design and authority review.',
                                 'Action areas are edge-connected flood-depth masks, not hydraulic catchments or verified retention sites.',
                                 'No hydraulic benefit, simultaneous flood volume, cooling, lifecycle cost or Pareto front is calculated.',
                                 'Heat is baseline context; ownership is a delivery category. Neither compensates for an unsafe pathway.',
                                 'The source grid is retained. The current 250,000-unit guard remains; partition larger analyses explicitly.',
                                 'Other NRW municipalities must replace and review the Köln rule profile.'])
    if config.get('demo'):
        manifest['limitations'].insert(0, 'SYNTHETIC DEMONSTRATION: not findings for Köln-Kalk.')
    (out/'run_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    (out/'resolved_config.json').write_text(json.dumps(config, indent=2, ensure_ascii=False))
    (out/'planning_summary.json').write_text(json.dumps(stats, indent=2))
    maps = [('intervention_need', '01 · Flood intervention need', 'status', None,
             'Depth at or above the registered\nthreshold identifies local need.\nUnknown cells remain unknown.\n\nBelow-threshold source-control\nareas are retained for investigation.\nThesis §§5.1, 5.5.1; user threshold.')]
    if actions:
        maps.append(('planning_action_areas', '02 · Flood action areas', 'action_class', None,
                     'Connected flood-need areas for\nplanning discussion. A001 etc.\nfollow depth, then area order.\n\nRead ownership shares, heat\noverlap and next action on click.\nThese are not design modules.\nNo flood benefit is estimated.'))
    maps += [('groundwater_screen', '03 · Infiltration evidence and restrictions', 'status', None,
              'Known prohibitions block infiltration.\nMissing evidence stays conditional.\n\nLined detention and controlled\noutlets remain separate concepts.\nFinal clearance needs module design.\nThesis §§5.4.2, 5.5.2; Köln (2022).'),
             ('ownership', '04 · Public and private delivery routes', 'status', None,
              'Exact polygon area shares.\nPrivate land is a partnership route.\nUnknown ownership is retained.\n\nPublic use is not proof of ownership.\nClick a unit for the next action.\nThesis §§5.4.1, 5.5.4.')]
    if heat:
        maps.append(('heat_context', '05 · Flood and heat planning context', 'status', None,
                     'Explicit source heat classes.\nBlue outlines: flood action areas.\nPriority overlap is recorded for\neach flood action area.\n\nThis is baseline heat targeting.\nNo temperature reduction is claimed.\nThesis §§4.2, 5.7.4.'))
    for key, (label, _, _) in FAMILIES.items():
        maps.append(('planning_opportunities', label, 'opportunity_class', f'"family" = \'{key}\'',
                     'Surface match identifies an\ninvestigation opportunity only.\nAll retained concepts are conditional.\n\nGrey: incompatible recorded surface.\nPurple: surface evidence missing.\nKnown infiltration FAIL is retained\nin the pathway field.\nThesis Table 4.2; §§5.5.1–5.5.4.'))
    if muriel:
        fields = dict(muriel_source_mask='mask_class', muriel_hotspots='hotspot_class', muriel_priority='planning_class', muriel_destinations='status', muriel_connections='line_kind')
        for table, title in [('muriel_source_mask', 'depth mask'), ('muriel_hotspots', 'hotspots'), ('muriel_priority', 'protect / investigate / adapt'), ('muriel_destinations', 'usable destinations'), ('muriel_connections', 'routing evidence')]:
            if any(name == table for name,_ in layers):
                maps.append((table, 'MURIEL · '+title, fields[table], None,
                             'Registered local Porz/Eil criteria.\nRead exact thresholds and decisions\nin the MURIEL registers.\n\nProximity is not a hydraulic route.\nNo infiltration clearance.\nSchwerdorf (2022), slides 19–20;\nthesis §§4.4.2, 5.5.3.'))
    control.phase(72, 'Building planning maps and project')
    exported = publish_maps(out, gpkg, crs, aoi, config, maps, export_maps, control)
    from .planning_report import create_planning_report
    create_planning_report(out, config, manifest, actions, exported)
    return out


def publish_maps(out, gpkg, crs, aoi, config, maps, export_maps, control):
    PALETTE.update(INVESTIGATE=('#e8b04a', 'Investigate · conditional planning concept'),
                   SURFACE_UNKNOWN=('#9b82ad', 'Surface class missing / mixed'), SURFACE_MISMATCH=('#dce2e7', 'Recorded surface does not match'),
                   REVIEW_FLOOD=('#286b9a', 'Flood action area · investigate'),
                   HEAT_PRIORITY=('#c06b53', 'Documented heat-priority context'), HEAT_OTHER=('#dce6df', 'Other documented heat class'), HEAT_UNKNOWN=('#c7c3cc', 'Unknown / conflicting heat evidence'))
    project = QgsProject(); project.setCrs(crs)
    outlines = None
    if any(table == 'heat_context' for table, *_ in maps) and any(table == 'planning_action_areas' for table, *_ in maps):
        from qgis.core import QgsFillSymbol, QgsSingleSymbolRenderer
        outlines = styled_layer(gpkg, 'planning_action_areas', 'Flood action outlines', 'action_class')
        outlines.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple({'style':'no', 'outline_color':'#245e86', 'outline_width':'0.7'})))
        project.addMapLayer(outlines)
    layers, pages, exported = [], [], []
    for i, (table, title, field, subset, notes) in enumerate(maps):
        control.update(72 + 12*i/len(maps), 'Preparing map: '+title)
        layer = styled_layer(gpkg, table, title, field, subset)
        project.addMapLayer(layer); layers.append(layer)
        if export_maps:
            layout = make_layout(project, layer, title, config, notes, aoi.boundingBox(), i+1)
            if outlines and table == 'heat_context':
                from qgis.core import QgsLayoutItemMap
                for item in layout.items():
                    if isinstance(item, QgsLayoutItemMap):
                        item.setLayers([outlines, layer])
            pages.append(layout)
            filename = f'{i+1:02d}_'+re.sub(r'[^A-Za-z0-9_-]', '_', title)+'.png'
            rendered = QgsLayoutExporter(layout).renderPageToImage(0, dpi=140)
            if rendered.isNull() or not rendered.save(str(out/filename), 'PNG'):
                raise RuntimeError('Cannot export planning map: '+filename)
            exported.append((title, filename))
    for name in ('decision_audit', 'source_registry', 'input_provenance'):
        layer = QgsVectorLayer(f'{gpkg}|layername={name}|option:NOLOCK=NO', name, 'ogr')
        if not layer.isValid():
            raise RuntimeError('Cannot reopen register '+name)
        project.addMapLayer(layer)
    tree = project.layerTreeRoot(); model = QgsLayerTreeModel(tree)
    if outlines:
        node = tree.findLayer(outlines.id()); clone = node.clone()
        tree.removeChildNode(node); tree.insertChildNode(0, clone)
    for visible in layers:
        for layer in layers:
            tree.findLayer(layer.id()).setItemVisibilityChecked(layer == visible)
        if outlines:
            tree.findLayer(outlines.id()).setItemVisibilityChecked(visible.name() == '05 · Flood and heat planning context')
        project.mapThemeCollection().insert(visible.name(), QgsMapThemeCollection.createThemeFromCurrentState(tree, model))
    for layer in layers:
        tree.findLayer(layer.id()).setItemVisibilityChecked(layer == layers[0])
    if outlines:
        tree.findLayer(outlines.id()).setItemVisibilityChecked(False)
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(aoi.boundingBox(), crs))
    project.setFilePathStorage(Qgis.FilePathType.Relative); project.setFileName(str(out/'stage1.qgz'))
    if not project.write():
        raise RuntimeError('Cannot save planning QGIS project.')
    pdfs = []
    for i, page in enumerate(pages):
        control.update(85+12*i/len(pages), f'Printing planning sheet {i+1}/{len(pages)}')
        path = out/f'_sheet_{i+1:02d}.pdf'; settings = QgsLayoutExporter.PdfExportSettings(); settings.dpi = 180
        if QgsLayoutExporter(page).exportToPdf(str(path), settings) != QgsLayoutExporter.Success:
            raise RuntimeError('Cannot print planning PDF.')
        pdfs.append(path)
    if pdfs and shutil.which('pdfunite'):
        subprocess.run(['pdfunite', *map(str, pdfs), str(out/'stage1_atlas.pdf')], check=True)
        muriel_pdfs = [p for p, page in zip(pdfs, pages) if 'MURIEL ·' in page.name()]
        if muriel_pdfs:
            subprocess.run(['pdfunite', *map(str, muriel_pdfs), str(out/'muriel_atlas.pdf')], check=True)
        for path in pdfs:
            path.unlink()
    return exported
