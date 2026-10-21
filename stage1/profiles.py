"""Jurisdiction-specific rule registration, independent of GIS and city data.

The thesis §5.9 transfers the workflow, not the local legal/technical values.
Generic projects intentionally have no numeric local rules. Source references
are bound to each decision; no process-global citation registry is mutated.
"""
from copy import deepcopy
import math
import re
import unicodedata

from .catalogue import DEFAULT_POLICY, KOELN_POLICY, SOURCES

SOURCE_ROLES = {'LOCAL_INFILTRATION':'infiltration', 'LOCAL_GROUNDWATER':'groundwater', 'LOCAL_ASSETS':'assets', 'LOCAL_ROOF':'roof',
                'KOELN2022':'infiltration', 'DWA_SUMMARY':'groundwater', 'STEB2025':'assets', 'ROOF2026':'roof'}
NUMERIC_ROLES = {'groundwater_floor_m':'groundwater', 'groundwater_preferred_m':'groundwater',
                 'neighbour_setback_m':'infiltration', 'basement_recommended_m':'infiltration', 'asset_clearance_m':'assets'}


def place_key(value):
    text = ''.join(c for c in unicodedata.normalize('NFKD', str(value or '')) if not unicodedata.combining(c)).strip().casefold()
    return 'koeln' if text in ('koln','koeln','cologne') else text


def profile_template(kind='generic'):
    if kind not in ('generic','koeln'):
        raise ValueError('Choose generic or koeln, or load a registered custom profile.')
    return deepcopy(KOELN_POLICY if kind == 'koeln' else DEFAULT_POLICY)


def _nonnegative(value, label):
    if isinstance(value, bool):
        raise ValueError(f'{label}: use a finite nonnegative number, not a Boolean.')
    try:
        numeric = float(value)
    except (TypeError,ValueError) as exc:
        raise ValueError(f'{label}: use a finite nonnegative number or null for an unconfigured rule.') from exc
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f'{label}: use a finite nonnegative number.')
    return numeric


def validate_policy(policy):
    if not isinstance(policy, dict):
        raise ValueError('policy: expected a rule-profile object.')
    legacy = policy.get('profile_id') == KOELN_POLICY['profile_id']
    kind = policy.get('profile_kind', 'koeln' if legacy else 'generic')
    if kind not in ('generic','koeln','custom'):
        raise ValueError('profile_kind: choose generic, koeln or custom.')
    p = {**profile_template('koeln' if kind == 'koeln' else 'generic'), **deepcopy(policy), 'profile_kind':kind}
    for key in ('profile_id','rule_scope','municipality','authority_label'):
        if not isinstance(p[key],str):
            raise ValueError(f'policy.{key}: enter text.')
    if not p['profile_id'].strip():
        raise ValueError('profile_id: enter a versioned profile identifier.')
    if not isinstance(p['profile_reviewed'],bool):
        raise ValueError('profile_reviewed must be a JSON boolean, never a string')
    if kind == 'koeln' and any(place_key(p[key]) != 'koeln' for key in ('rule_scope','municipality')):
        raise ValueError('The Köln profile applies only to Köln. For another jurisdiction choose generic or a separately registered custom profile; a review checkbox does not transfer Köln law.')
    if p['rule_scope'] and place_key(p['municipality']) != place_key(p['rule_scope']):
        raise ValueError('Profile jurisdiction and rule_scope differ. Register a profile for the actual governing jurisdiction.')
    if kind == 'custom' and (not p['rule_scope'].strip() or p['profile_id'] in (DEFAULT_POLICY['profile_id'],KOELN_POLICY['profile_id'])):
        raise ValueError('A custom profile needs its own profile_id and governing rule_scope / municipality.')
    for key in NUMERIC_ROLES:
        if p[key] is not None:
            p[key] = _nonnegative(p[key],key)
    floor, preferred = p['groundwater_floor_m'], p['groundwater_preferred_m']
    if (floor is None) != (preferred is None):
        raise ValueError('Register both groundwater floor and preferred separation, or leave both null.')
    if floor is not None and floor > preferred:
        raise ValueError('Groundwater floor must not exceed preferred clearance')
    for key in ('neighbour_setback_recommended','basement_setback_recommended','asset_clearance_recommended'):
        if not isinstance(p[key],bool):
            raise ValueError(f'{key}: use a Boolean to distinguish a recommendation from a hard minimum.')
    if p['groundwater_intermediate_action'] not in ('FAIL','CONDITIONAL','EXCEPTION'):
        raise ValueError('groundwater_intermediate_action: select FAIL, CONDITIONAL or EXCEPTION for the floor-to-preferred band.')
    fields=p['groundwater_exception_fields']
    if not isinstance(fields,list) or any(not isinstance(f,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',f) for f in fields):
        raise ValueError('groundwater_exception_fields: use a list of documented Boolean evidence field names.')
    if p['groundwater_intermediate_action']=='EXCEPTION' and not fields:
        raise ValueError('An exception route needs its explicitly registered evidence fields.')
    zones = p['protection_zones']
    if zones is not None:
        if not isinstance(zones,dict) or set(zones) != {'excluded','outer','outside','shaft_excluded'}:
            raise ValueError('protection_zones: register excluded, outer, outside and shaft_excluded code lists, or null.')
        for key, codes in zones.items():
            if not isinstance(codes,list) or any(not isinstance(c,str) or not c.strip() for c in codes):
                raise ValueError('Protection-zone categories must be nonempty text codes in lists.')
            zones[key] = [c.upper().replace(' ','') for c in codes]
        groups = [set(zones[key]) for key in ('excluded','outer','outside')]
        if any(groups[i] & groups[j] for i in range(3) for j in range(i+1,3)):
            raise ValueError('Protection-zone categories overlap; excluded, outer and outside must be disjoint.')
    bands = p['sewer_strip_bands']
    if not isinstance(bands,list) or any(not isinstance(b,dict) or set(b) != {'min_diameter_cm','total_width_m'} for b in bands):
        raise ValueError('sewer_strip_bands: use minimum-diameter / total-width objects, or an empty list.')
    for band in bands:
        for key in band:
            band[key] = _nonnegative(band[key], 'sewer_strip_bands.'+key)
    if bands and (bands[0]['min_diameter_cm'] != 0 or any(a['min_diameter_cm'] >= b['min_diameter_cm'] for a,b in zip(bands,bands[1:]))):
        raise ValueError('Sewer bands must start at zero and have increasing unique minimum diameters.')
    if not isinstance(p['references'],dict) or not isinstance(p['rule_sources'],dict):
        raise ValueError('references and rule_sources must be objects.')
    for source_id, reference in p['references'].items():
        if source_id in SOURCES:
            raise ValueError('Custom references cannot replace built-in source IDs; use a new source ID.')
        if not isinstance(reference,dict) or any(not isinstance(reference.get(k),str) or not reference[k].strip() for k in ('citation','locator','status')):
            raise ValueError(f'{source_id}: provide citation, locator and verification status for a local rule source.')
        reference.setdefault('url','')
        if not isinstance(reference['url'],str):
            raise ValueError(f'{source_id}.url must be text.')
    for role, source in p['rule_sources'].items():
        if role not in set(SOURCE_ROLES.values()) or not isinstance(source,str) or source not in {**SOURCES, **p['references']}:
            raise ValueError(f'Unregistered rule source for {role}; provide its full citation in references.')
        if kind != 'koeln' and source in ('KOELN2022','STEB2025','ROOF2026'):
            raise ValueError('Köln municipal sources cannot be a governing rule source for a generic/custom jurisdiction. Register the actual local source.')
    configured_roles = {role for key,role in NUMERIC_ROLES.items() if p[key] is not None}
    if zones is not None: configured_roles.add('infiltration')
    if bands: configured_roles.add('assets')
    p['unreferenced_rule_roles'] = sorted(role for role in configured_roles if p['rule_sources'].get(role) in (None,'THESIS','USER_DEPTH'))
    if p['profile_reviewed'] and (not p['profile_review_ref'] or not p['rule_scope'] or p['unreferenced_rule_roles']):
        raise ValueError('A reviewed profile needs a governing jurisdiction, dated review reference and cited sources for every configured local rule.')
    return p


def governing_source(policy, source_id):
    role = SOURCE_ROLES.get(source_id)
    if role:
        source_id = policy['rule_sources'].get(role,'THESIS')
    return source_id, policy['references'].get(source_id) or SOURCES[source_id]


def source_registry(config):
    policy = config['policy']
    sources = {key:SOURCES[key] for key in ('THESIS','USER_DEPTH')}
    for source in policy['rule_sources'].values():
        sources[source] = policy['references'].get(source) or SOURCES[source]
    sources.update(policy['references'])
    muriel = config.get('muriel') or {}
    if muriel.get('enabled'):
        sources['MURIEL'] = SOURCES['MURIEL']
        if muriel.get('criteria_source'):
            sources['MURIEL_CRITERIA'] = muriel['criteria_source']
    return sources


def profile_snapshot(config):
    return {'jurisdiction':config.get('jurisdiction') or config['policy']['municipality'],
            'profile':deepcopy(config['policy']), 'flood_threshold_m':config['flood_threshold_m'],
            'flood_threshold_reference':config.get('flood_threshold_reference','Unreferenced project threshold'),
            'scenario_id':config['scenario_id'], 'stated_return_period_years':config.get('stated_return_period_years'),
            'muriel':{key:deepcopy((config.get('muriel') or {}).get(key)) for key in
                      ('enabled','thresholds','criteria_profile_id','criteria_scope','criteria_adoption_ref','criteria_source')}}
