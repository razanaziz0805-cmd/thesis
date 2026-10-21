"""Spatial MURIEL screen: flood footprints, destinations and evidence-backed routes."""

import hashlib
import json
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsSpatialIndex, QgsWkbTypes

from .catalogue import SOURCES
from .engine import Decision, aggregate, evaluate_muriel, muriel_settings, number, truth


def union(geometries):
    geoms = [g for g in geometries if g is not None and not g.isEmpty()]
    return QgsGeometry.unaryUnion(geoms) if geoms else QgsGeometry()


def polygon_parts(geom):
    if geom.isEmpty():
        return []
    if geom.type() != QgsWkbTypes.PolygonGeometry:
        raise ValueError('MURIEL requires polygon flood/land/road/space inputs')
    return [QgsGeometry.fromPolygonXY(p) for p in geom.asMultiPolygon()] if geom.isMultipart() else [QgsGeometry(geom)]


def flood_hotspots(units, aoi, settings=None):
    """Dissolve wet cells/partition pieces, retaining holes and edge connectivity.

    Polygon union keeps corner-touching parts separate. The source mask is
    registered: default depth_mask uses >0.30 m cells; inundation_maximum uses
    the declared wet-extent threshold then tests maximum depth separately.
    """
    p = muriel_settings(settings)
    cutoff = p['min_max_depth_m'] if p['footprint_mode'] == 'depth_mask' else p['flood_extent_depth_m']
    wet = [u for u in units if number(u['attrs'].get('flood_depth_m')) is not None and u['attrs']['flood_depth_m'] > cutoff]
    if not wet:
        return []
    idx = QgsSpatialIndex()
    for i, u in enumerate(wet):
        f = QgsFeature(i); f.setGeometry(u['geometry']); idx.addFeature(f)
    uncovered = aoi.difference(union(u['geometry'] for u in units))
    unknown = union([uncovered, *(u['geometry'] for u in units if number(u['attrs'].get('flood_depth_m')) is None)])
    boundary = QgsGeometry(aoi.constGet().boundary())
    parts = polygon_parts(union(u['geometry'] for u in wet))
    parts.sort(key=lambda g: (g.boundingBox().yMinimum(), g.boundingBox().xMinimum(), g.area()))
    results = []
    for count, geom in enumerate(parts, 1):
        members = [wet[i] for i in idx.intersects(geom.boundingBox()) if geom.intersection(wet[i]['geometry']).area() > 1e-8]
        canonical = QgsGeometry(geom); canonical.normalize()
        ident = 'MUR_' + hashlib.sha256(bytes(canonical.asWkb())).hexdigest()[:12]
        edge = geom.distance(boundary) <= 1e-7
        nodata = not unknown.isEmpty() and geom.distance(unknown) <= 1e-7
        results.append({'geometry': geom, 'hotspot_id': ident, 'hotspot_label': f'M{count:02d}',
                        'area_m2': geom.area(), 'max_depth_m': max(u['attrs']['flood_depth_m'] for u in members),
                        'source_unit_ids': sorted({u['attrs']['unit_id'] for u in members}),
                        'boundary_incomplete': edge or nodata,
                        'extent_note': '; '.join(s for flag, s in [(edge, 'Touches AOI boundary'), (nodata, 'Adjacent to NoData')] if flag) or 'Interior, known adjacent depth coverage'})
    return results


def _inventory(spec, crs, geometry_type=QgsWkbTypes.PolygonGeometry, control=None):
    from .gis import load_vector
    if not spec:
        return [], False
    items = load_vector(spec, crs, allow_empty=True, control=control)
    if any(g.type() != geometry_type for g, _ in items):
        raise ValueError(f'MURIEL input has wrong geometry type: {spec["path"]} / {spec.get("layer")}')
    return items, spec.get('coverage_complete') is True


def _minimum(geom, records):
    return min((geom.distance(g) for g, _ in records), default=None)


class SpatialLookup:
    """Exact polygon distances with an R-tree; bounding boxes are only filters."""
    def __init__(self, records):
        self.records = records
        self.index = QgsSpatialIndex(flags=QgsSpatialIndex.FlagStoreFeatureGeometries)
        for i, (geom, _) in enumerate(records):
            f = QgsFeature(i)
            f.setGeometry(geom)
            self.index.addFeature(f)

    def minimum(self, geom):
        ids = self.index.nearestNeighbor(geom, 1)
        if not ids:
            return None
        # Provider/QGIS versions can rank polygon nearest neighbours by a box
        # lower bound (notably with holes). Any initial candidate gives a safe
        # upper bound; search every box within that bound and measure geometry.
        upper = min(geom.distance(self.records[i][0]) for i in ids)
        extent = geom.boundingBox()
        extent.grow(upper + 1e-8)
        return min(geom.distance(self.records[i][0]) for i in self.index.intersects(extent))

    def within(self, geom, radius):
        extent = geom.boundingBox()
        extent.grow(radius)
        return [self.records[i][1] for i in sorted(self.index.intersects(extent))
                if geom.distance(self.records[i][0]) <= radius]


def _reference(spec):
    return (spec or {}).get('evidence_ref') or 'MISSING_SOURCE_REFERENCE'


def _route_checks(hotspot, destination, routes, spec):
    """Evaluate every explicit line; absence remains an investigation branch."""
    from .gis import summary
    rows_out = []
    matches = [(g, a) for g, a in routes if str(a.get('hotspot_id')) == hotspot['hotspot_id'] and str(a.get('destination_id')) == destination['destination_id']]
    for index, (geom, a) in enumerate(matches, 1):
        ref = str(a.get('evidence_ref') or _reference(spec))
        checks = []
        def add(rid, state, reason, observed, expected, closure):
            checks.append(Decision(rid, state, reason, str(observed), expected, 'THESIS', ref,
                                   'Survey / drainage designer / land-rights evidence owner', closure))
        parts = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
        vertices = parts[0] if len(parts) == 1 else []
        endpoint_ok = len(vertices) >= 2 and geom.length() > 1e-7 and hotspot['geometry'].distance(QgsGeometry.fromPointXY(vertices[0])) <= 1e-7 and destination['geometry'].distance(QgsGeometry.fromPointXY(vertices[-1])) <= 1e-7
        add('MURIEL_ROUTE_ENDPOINTS', 'ADMISSIBLE' if endpoint_ok else 'FAIL', 'Directed line starts at hotspot and ends in the selected destination', endpoint_ok, 'Single directed line, nonzero length, matching geometric endpoints', 'Correct the route geometry and direction; a line to another site is not evidence for this pair.')
        add('MURIEL_ROUTE_REFERENCE', 'ADMISSIBLE' if ref != 'MISSING_SOURCE_REFERENCE' else 'CONDITIONAL', 'Dated route evidence reference', ref, 'Survey / assessment reference', 'Link the assessment to dated evidence.')
        for field in ('topography_compatible', 'flow_routing_safe', 'downstream_receptors_safe', 'route_land_control_ok'):
            v = truth(a.get(field))
            state = 'CONDITIONAL' if v is None else 'ADMISSIBLE' if v else 'CONDITIONAL' if field == 'route_land_control_ok' else 'FAIL'
            add('MURIEL_ROUTE_' + field.upper(), state, field.replace('_', ' '), a.get(field), 'Documented compatible / safe / controlled', 'Provide specific surveyed topographic, flow, downstream-safety and rights evidence; redesign incompatible routes.')
        status = aggregate(checks)
        rows_out.append(({'hotspot_id': hotspot['hotspot_id'], 'hotspot_label': hotspot['hotspot_label'], 'destination_id': destination['destination_id'],
                          'connection_id': f'{hotspot["hotspot_id"]}_{destination["destination_id"]}_{index}',
                          'line_kind': 'VERIFIED_ROUTE' if status == 'ADMISSIBLE' else 'REJECTED_ROUTE' if status == 'FAIL' else 'UNVERIFIED_ROUTE',
                          'distance_m': hotspot['geometry'].distance(destination['geometry']), 'evidence_ref': ref,
                          **summary(checks)}, geom, checks))
    if not matches:
        line = hotspot['geometry'].shortestLine(destination['geometry'])
        if line.length() <= 1e-7:
            line = QgsGeometry()  # overlapping polygons have no nonzero proximity connector
        d = Decision('MURIEL_PROXIMITY_ONLY', 'CONDITIONAL',
                     'Straight shortest-distance connector is a map aid, not a surveyed hydraulic route',
                     str(hotspot['geometry'].distance(destination['geometry'])), 'Topographic, safe-flow and rights evidence for this pair',
                     'MURIEL', 'No route evidence supplied', 'Survey / drainage designer', 'Survey a specific route and assess inlet, levels, outlet, exceedance, receptors and rights.')
        rows_out.append(({'hotspot_id': hotspot['hotspot_id'], 'hotspot_label': hotspot['hotspot_label'], 'destination_id': destination['destination_id'],
                          'connection_id': f'{hotspot["hotspot_id"]}_{destination["destination_id"]}_proximity',
                          'line_kind': 'PROXIMITY_ONLY', 'distance_m': hotspot['geometry'].distance(destination['geometry']), 'evidence_ref': 'MISSING',
                          **summary([d])}, line, [d]))
    return rows_out


def screen(units, aoi, crs, config, groundwater_records, control=None):
    """Return spatial layers and audit rows to the existing Stage 1 pipeline."""
    from .gis import summary
    spec = config['muriel']
    p = muriel_settings(spec.get('thresholds'))
    hotspots = flood_hotspots(units, aoi, p)
    source_specs = [(f'muriel_receptors_{i+1}', s) for i, s in enumerate(spec.get('receptors', []))]
    receptor_items, receptor_complete = [], bool(spec.get('receptors'))
    for _, source in source_specs:
        items, complete = _inventory(source, crs, control=control)
        receptor_items.extend(items); receptor_complete &= complete
    land, land_complete = _inventory(spec.get('municipal_land'), crs, control=control)
    land_source = spec.get('municipal_land') or {}
    if land_source.get('class_field'):
        values = land_source.get('municipal_values')
        if not values:
            raise ValueError('MURIEL municipal class filtering requires municipal_values')
        field = land_source['class_field']
        land_complete &= all(a.get(field) is not None for _, a in land)
        accepted = {str(v) for v in values}
        others = union(g for g, a in land if str(a.get(field)) not in accepted)
        selected = [(g, a) for g, a in land if str(a.get(field)) in accepted]
        if not others.isEmpty():
            # A conflicting private/unknown claim cannot become public space
            # merely by selecting the municipal row from an overlapping layer.
            land_complete &= not any(g.intersection(others).area() > 1e-8 for g, _ in selected)
            selected = [(g.difference(others), a) for g, a in selected if g.difference(others).area() > 1e-8]
        land = selected
    land_verified = (spec.get('municipal_land') or {}).get('municipal_verified') is True
    roads, roads_complete = _inventory(spec.get('roads'), crs, control=control)
    public = union(g for g, _ in land) if land_verified else QgsGeometry()
    public_nonroad = public.difference(union(g for g, _ in roads)) if roads and not public.isEmpty() else public
    # Positive evidence requires the road inventory too: unknown roads cannot
    # establish that a specific municipal polygon is non-road.
    nonroad_known = land_verified and roads_complete
    public_records = [(g, {}) for g in polygon_parts(public_nonroad)] if nonroad_known else []
    usable, usable_complete = _inventory(spec.get('usable_space'), crs, control=control)
    usable_source = spec.get('usable_space') or {}
    id_field, usable_field = usable_source.get('id_field', 'destination_id'), usable_source.get('usable_field', 'usable')
    ids, destinations, unknown_usability = set(), [], False
    for geom, a in usable:
        ident = a.get(id_field)
        if ident is None or not str(ident).strip() or str(ident) in ids:
            raise ValueError('MURIEL usable spaces require unique, nonempty destination IDs')
        ident = str(ident); ids.add(ident)
        raw = a.get(usable_field)
        state = truth(usable_source['usable_mapping'].get(str(raw))) if usable_source.get('usable_mapping') else truth(raw)
        unknown_usability |= state is None
        if state is True and nonroad_known and not public_nonroad.isEmpty():
            eligible = geom.intersection(public_nonroad)
            if eligible.area() > 1e-8:
                destinations.append({'destination_id': ident, 'geometry': eligible, 'original_area_m2': geom.area(),
                                     'eligible_area_m2': eligible.area(), 'source_usable_value': str(raw), 'evidence_ref': a.get('evidence_ref') or _reference(usable_source)})
    # Land/road coverage must extend through the 100 m search area, not stop at
    # the AOI. Missing coverage never establishes absence of a destination.
    municipal_complete = land_complete and land_verified and roads_complete
    destination_complete = usable_complete and municipal_complete and not unknown_usability
    eligible_union = union(d['geometry'] for d in destinations)
    route_items, _ = _inventory(spec.get('routes'), crs, QgsWkbTypes.LineGeometry, control=control)
    routes_by_pair = {}
    for geom, a in route_items:
        routes_by_pair.setdefault((str(a.get('hotspot_id')), str(a.get('destination_id'))), []).append((geom, a))
    receptor_lookup = SpatialLookup(receptor_items)
    public_lookup = SpatialLookup(public_records)
    destination_lookup = SpatialLookup([(d['geometry'], d) for d in destinations])
    valid_hotspots, valid_destinations = {h['hotspot_id'] for h in hotspots}, {d['destination_id'] for d in destinations}
    ineligible_routes = []
    hotspot_map = {h['hotspot_id']: h for h in hotspots}
    destination_map = {d['destination_id']: d for d in destinations}
    for geom, a in route_items:
        if str(a.get('hotspot_id')) not in valid_hotspots or str(a.get('destination_id')) not in ids:
            raise ValueError('MURIEL route references an unknown hotspot or source destination; check IDs and current screening inputs')
        if str(a.get('destination_id')) not in valid_destinations:
            ineligible_routes.append((geom, a, False))
        elif hotspot_map[str(a['hotspot_id'])]['geometry'].distance(destination_map[str(a['destination_id'])]['geometry']) > p['destination_distance_m']:
            ineligible_routes.append((geom, a, True))
    gw_map = {a['unit_id']: a['status'] for a, _ in groundwater_records}
    hotspot_records, priority_records, connection_records, audit, destination_records = [], [], [], [], []
    for index, (geom, a, outside_radius) in enumerate(ineligible_routes, 1):
        state = 'FAIL' if destination_complete or outside_radius else 'CONDITIONAL'
        ref = str(a.get('evidence_ref') or _reference(spec.get('routes')))
        d = Decision('MURIEL_ROUTE_PAIR_RADIUS' if outside_radius else 'MURIEL_ROUTE_DESTINATION_ELIGIBILITY', state,
                     'Declared route is outside the registered destination search radius' if outside_radius else 'Declared route destination is not currently verified usable municipal non-road land; route cannot confer eligibility',
                     str(a.get('destination_id')), 'Eligible destination geometry plus complete ownership, road and usability evidence',
                     'MURIEL', ref, 'Source data / land / design evidence owner',
                     'Resolve missing evidence or select an eligible destination; retain this rejected or conditional line in the audit.')
        ident = f'{a["hotspot_id"]}_{a["destination_id"]}_ineligible_{index}'
        connection_records.append(({'hotspot_id':str(a['hotspot_id']),'hotspot_label':next(h['hotspot_label'] for h in hotspots if h['hotspot_id']==str(a['hotspot_id'])),
                                    'destination_id':str(a['destination_id']),'connection_id':ident,
                                    'line_kind':'REJECTED_ROUTE' if state=='FAIL' else 'UNVERIFIED_ROUTE',
                                    'distance_m':None,'evidence_ref':ref,'scenario_id':config['scenario_id'],'run_id':config['run_id'],
                                    'is_demo':int(config.get('demo',False)),**summary([d])},geom))
        audit.append({'unit_id':ident,'design':'MURIEL_ROUTE','scenario_id':config['scenario_id'],**d.record()})
    source_mask = []
    cutoff = p['min_max_depth_m'] if p['footprint_mode'] == 'depth_mask' else p['flood_extent_depth_m']
    for unit_index, unit in enumerate(units):
        if control and unit_index % 128 == 0:
            control.check()
        a = unit['attrs']; depth = number(a.get('flood_depth_m'))
        included = depth is not None and depth > cutoff
        d = Decision('MURIEL_SOURCE_MASK', 'CONDITIONAL' if depth is None else 'ADMISSIBLE' if included else 'NOT_APPLICABLE',
                     'Source flood cell/polygon included in registered MURIEL extent' if included else 'NoData is unknown' if depth is None else 'Depth does not exceed registered MURIEL extent threshold',
                     str(depth), f'> {cutoff:g} m; footprint_mode={p["footprint_mode"]}',
                     'MURIEL' if p['footprint_mode'] == 'depth_mask' else 'THESIS', 'Flood input; see checksummed input_provenance',
                     'Flood-data provider / researcher', 'Resolve depth NoData; do not convert it to dry land.' if depth is None else 'No additional closure for this source-mask observation')
        if d.source_id == 'MURIEL' and spec.get('criteria_source'):
            d.source_id, d.reference = 'MURIEL_CRITERIA', spec['criteria_source']
        source_mask.append(({'unit_id':a['unit_id'],'flood_depth_m':depth,'mask_class':'DEPTH_UNKNOWN' if depth is None else 'DEPTH_INCLUDED' if included else 'DEPTH_EXCLUDED',
                             'threshold_m':cutoff,'footprint_mode':p['footprint_mode'],'scenario_id':config['scenario_id'],'is_demo':int(config.get('demo',False)),**summary([d])},unit['geometry']))
        audit.append({'unit_id':a['unit_id'],'design':'MURIEL_SOURCE_MASK','scenario_id':config['scenario_id'],**d.record()})
    for h in hotspots:
        if control:
            control.check()
        geom = h['geometry']
        near = destination_lookup.within(geom, p['destination_distance_m'])
        links = []
        for d in near:
            links.extend(_route_checks(h, d, routes_by_pair.get((h['hotspot_id'], d['destination_id']), []), spec.get('routes')))
        states = [row[0]['status'] for row in links]
        best_route = 'ADMISSIBLE' if 'ADMISSIBLE' in states else 'CONDITIONAL' if not states or 'CONDITIONAL' in states else 'FAIL'
        groundwater_states = [gw_map.get(uid, 'CONDITIONAL') for uid in h['source_unit_ids']]
        gw_state = 'FAIL' if 'FAIL' in groundwater_states else 'CONDITIONAL' if 'CONDITIONAL' in groundwater_states else 'ADMISSIBLE'
        metrics = {k: v for k, v in h.items() if k != 'geometry'}
        metrics.update(receptor_distance_m=receptor_lookup.minimum(geom), receptor_coverage_complete=receptor_complete,
                       municipal_distance_m=public_lookup.minimum(geom), municipal_coverage_complete=municipal_complete,
                       destination_distance_m=destination_lookup.minimum(geom),
                       destination_coverage_complete=destination_complete,
                       overlap_fraction=geom.intersection(eligible_union).area()/geom.area() if not eligible_union.isEmpty() else 0.,
                       overlap_coverage_complete=destination_complete, best_route_status=best_route,
                       route_note=f'{len(links)} explicit / proximity connection records; route evidence is independent of distance',
                       preliminary_infiltration_status=gw_state,
                       evidence_ref='; '.join(_reference(s) for _, s in source_specs) + '; ' + '; '.join(_reference(spec.get(k)) for k in ('municipal_land', 'roads', 'usable_space')))
        metrics.update(criteria_applicability_required=True, criteria_adoption_ref=spec.get('criteria_adoption_ref'),
                       criteria_scope_matches=spec.get('criteria_scope_matches',False), criteria_profile_id=spec.get('criteria_profile_id'),
                       criteria_source=spec.get('criteria_source'))
        planning, decisions = evaluate_muriel(metrics, p)
        # Source inventory references are retained per gate, rather than merely
        # attaching one citation to the whole map.
        refs = {'MURIEL_RECEPTOR': '; '.join(_reference(s) for _, s in source_specs),
                'MURIEL_MUNICIPAL': _reference(spec.get('municipal_land')) + '; ' + _reference(spec.get('roads')),
                'MURIEL_DESTINATION': _reference(usable_source), 'MURIEL_RETENTION_FUNCTION': _reference(usable_source)}
        for d in decisions:
            d.evidence_ref = refs.get(d.rule_id, d.evidence_ref)
        base = {**{k:v for k,v in metrics.items() if k != 'criteria_source'}, 'source_unit_ids': json.dumps(h['source_unit_ids']), 'planning_class': planning,
                'overlap_percent': metrics['overlap_fraction']*100, 'nearby_destination_ids': '; '.join(d['destination_id'] for d in near),
                'scenario_id': config['scenario_id'], 'run_id': config['run_id'], 'is_demo': int(config.get('demo', False)), **summary(decisions)}
        priority_records.append((base, geom))
        threshold_rows = [d for d in decisions if d.rule_id in ('MURIEL_AREA', 'MURIEL_MAX_DEPTH', 'MURIEL_EXTENT_EVIDENCE')]
        hotspot_records.append(({**base, 'hotspot_class': 'EXTENT_UNCERTAIN' if h['boundary_incomplete'] else 'QUALIFYING_HOTSPOT' if all(d.status == 'ADMISSIBLE' for d in threshold_rows) else 'BELOW_SCREEN', **summary(threshold_rows)}, geom))
        for d in decisions:
            audit.append({'unit_id': h['hotspot_id'], 'design': 'MURIEL', 'scenario_id': config['scenario_id'], **d.record()})
        for attributes, line, rows in links:
            connection_records.append(({**attributes, 'scenario_id': config['scenario_id'], 'run_id': config['run_id'], 'is_demo': int(config.get('demo', False))}, line))
            for d in rows:
                audit.append({'unit_id': attributes['connection_id'], 'design': 'MURIEL_ROUTE', 'scenario_id': config['scenario_id'], **d.record()})
    for d in destinations:
        explanation = ('Usable-space polygon intersected with verified municipal ownership and the complete polygon road inventory subtracted. '
                       'This is available planning space, not approval or proven hydraulic capacity. '
                       f'Source: {SOURCES["MURIEL"]["citation"]}; {SOURCES["MURIEL"]["url"]}. '
                       f'Evidence: {d["evidence_ref"]}; municipal: {_reference(spec.get("municipal_land"))}; roads: {_reference(spec.get("roads"))}.')
        destination_records.append(({k: v for k, v in d.items() if k != 'geometry'} | {'status': 'USABLE_SPACE', 'explanation': explanation}, d['geometry']))
    context = []
    for kind, items in [('MUNICIPAL_CONTEXT', public_records), ('FLOOD_CONTEXT', [(h['geometry'], {'context_label':h['hotspot_label']}) for h in hotspots]), ('ROAD_CONTEXT', roads), ('BUILDING_CONTEXT', receptor_items)]:
        for geom, attributes in items:
            context.append(({'context_type': kind, 'context_label':attributes.get('context_label'), 'explanation': f'{kind}; context only. Source records and checksums are in input_provenance. {SOURCES["MURIEL"]["citation"]}.'}, geom))
    source_specs.extend((f'muriel_{k}', spec[k]) for k in ('municipal_land', 'roads', 'usable_space', 'routes') if spec.get(k))
    return {'source_mask': source_mask, 'hotspots': hotspot_records, 'priority': priority_records, 'destinations': destination_records,
            'connections': connection_records, 'context': context, 'audit': audit, 'sources': source_specs,
            'summary': {'enabled': True, 'thresholds': p,
                        'criteria_registration': {key:spec.get(key) for key in ('criteria_profile_id','criteria_scope','criteria_adoption_ref','criteria_scope_matches','criteria_source')},
                        'footprint_definition': f'Edge-connected source polygons/cells at depth >{p["min_max_depth_m"] if p["footprint_mode"] == "depth_mask" else p["flood_extent_depth_m"]:g} m; mode={p["footprint_mode"]}',
                        'footprint_count': len(hotspots), 'destination_count': len(destinations), 'connection_count': len(connection_records),
                        'unknown_source_unit_count': sum(a['mask_class']=='DEPTH_UNKNOWN' for a,_ in source_mask),
                        'planning_counts': {k: sum(a['planning_class'] == k for a, _ in priority_records) for k in sorted({a['planning_class'] for a, _ in priority_records})}}}
