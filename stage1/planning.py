"""Phase C planning choices, deliberately distinct from final admissibility.

Source: uploaded thesis §§5.1, 5.5.1–5.5.4 and Table 4.2. This palette is
an implementation of its mechanisms, not a new technical design standard.
"""
from .engine import intervention_need


FAMILIES = {
    'roof_control': ('Roof retention / greening', {'roof'}, 'Structural loading, waterproofing, drainage and emergency overflow'),
    'rain_garden': ('Rain gardens / planted detention', {'open_space', 'verge'}, 'Available footprint, runoff quality, inlet, outlet and maintenance'),
    'tree_street': ('Water-sensitive trees / street retrofit', {'open_space', 'verge', 'pavement', 'parking', 'footway'}, 'Rootable space, utilities, access, inlet and safe overflow'),
    'multifunctional_space': ('Multifunctional detention space', {'open_space', 'pavement', 'parking'}, 'Existing retention, compatible normal use, safe routing and operator'),
    'permeable_surface': ('Permeable / underdrained surfaces', {'pavement', 'parking', 'footway'}, 'Traffic load, runoff quality, sub-base, outlet and de-clogging'),
}


def opportunity(attrs, family, groundwater_status, threshold_m):
    """A plausible surface match is CONDITIONAL, never a design PASS."""
    label, surfaces, checks = FAMILIES[family]
    land = attrs.get('land_type')
    need = intervention_need(attrs.get('flood_depth_m'), threshold_m)
    if land not in set().union(*(f[1] for f in FAMILIES.values())):
        kind, status, code = 'SURFACE_UNKNOWN', 'CONDITIONAL', 'PL_SURFACE_UNKNOWN'
        why = 'Surface class is missing, mixed or unmapped; no typology is selected.'
        next_action = 'Add or verify a classified surface polygon layer before selecting a typology.'
    elif land not in surfaces:
        kind, status, code = 'SURFACE_MISMATCH', 'NOT_APPLICABLE', 'PL_SURFACE_MISMATCH'
        why = f'The recorded {land} surface does not match this planning family.'
        next_action = 'Investigate a matching family; record any proposed land-use conversion separately.'
    else:
        kind, status, code = 'INVESTIGATE', 'CONDITIONAL', 'PL_INVESTIGATE'
        why = f'The recorded {land} surface supports investigation of {label.lower()}.'
        next_action = checks + '; document the water pathway and land control before module design.'
    if family == 'roof_control':
        pathway = 'Roof storage / controlled drainage; structural and outlet evidence outstanding.'
        infiltration_status = 'NOT_APPLICABLE'
    elif groundwater_status == 'FAIL':
        pathway = 'Infiltration excluded by a known gate; investigate a separate lined / controlled-release design.'
        infiltration_status = 'FAIL'
    else:
        pathway = 'Lined / controlled-release concept; infiltration remains conditional pending groundwater, soil and water-quality evidence.'
        infiltration_status = 'CONDITIONAL'
    context = ('Within the flood-need mask; this does not prove hydraulic connection.' if need == 'YES' else
               'Below the local flood threshold; retain as source-control investigation, with contributing-area connection unverified.' if need == 'NO' else
               'Flood depth is unknown; flood targeting cannot be established here.')
    return dict(family=family, family_label=label, opportunity_class=kind, status=status,
                reason_code=code, land_type=land or 'unknown', need_local=need,
                infiltration_status=infiltration_status, pathway=pathway, next_action=next_action,
                source_ids='THESIS; KOELN2022', reference='Thesis Table 4.2; §§5.1, 5.5.1–5.5.4; Stadt Köln (2022), as cited in thesis',
                explanation=f'{code}: {why}\n{context}\n{pathway}\nNext: {next_action}\n'
                            'Basis: thesis Table 4.2 and §§5.1, 5.5.1–5.5.4. City rules are locally scoped and require current review. '
                            'Planning opportunity only: no final admissibility or simulated benefit.')


def delivery_action(owner):
    return {
        'municipal': 'Coordinate a municipal public-space feasibility review with Stadt Köln / StEB; verify access and operator.',
        'private': 'Engage the landowner and assess a voluntary agreement, advice and the applicable funding route.',
        'other_public': 'Coordinate with the responsible public landowner and Stadt Köln / StEB.',
        'mixed': 'Agree a joint public/private delivery approach; retain the mapped ownership shares.',
        'conflict': 'Resolve overlapping ownership evidence before assigning a delivery route.',
    }.get(owner, 'Obtain current cadastral ownership evidence before assigning a delivery route.')
