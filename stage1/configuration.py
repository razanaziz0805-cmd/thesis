"""Configuration handling shared by the command line and QGIS panel."""
from copy import deepcopy
import json
from pathlib import Path

from .catalogue import DESIGNS, SOURCES
from .profiles import place_key, profile_template
from .engine import MURIEL_DEFAULTS, intervention_need, muriel_settings, validate_policy


def input_specs(config):
    for role in ('flood', 'study_area', 'ownership'):
        if config.get(role):
            yield role, config[role]
    for role in ('evidence', 'raster_evidence', 'distance_evidence'):
        for i, spec in enumerate(config.get(role, [])):
            yield f'{role}[{i}]', spec
    for role in ('surfaces', 'heat', 'restrictions'):
        if (config.get('planning') or {}).get(role):
            yield 'planning.' + role, config['planning'][role]
    m = config.get('muriel') or {}
    if m.get('enabled') is True:
        for i, spec in enumerate(m.get('receptors', [])):
            yield f'muriel.receptors[{i}]', spec
        for role in ('municipal_land', 'roads', 'usable_space', 'routes'):
            if m.get(role):
                yield f'muriel.{role}', m[role]


def load_data(source):
    if isinstance(source, dict):
        return deepcopy(source)
    try:
        return json.loads(Path(source).read_text(encoding='utf-8-sig'))
    except json.JSONDecodeError as exc:
        raise ValueError(f'Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}') from exc
    except OSError as exc:
        raise ValueError(f'Cannot read configuration: {exc}') from exc


def structure_errors(config):
    """Collect independent errors so users can correct them together."""
    if not isinstance(config, dict):
        return ['Configuration must be a JSON object.']
    errors = []
    if config.get('mode', 'engineering') not in ('planning', 'engineering'):
        errors.append('mode: select planning or engineering.')
    planning = config.get('planning') or {}
    if not isinstance(planning, dict):
        errors.append('planning: expected an object.')
    else:
        for role in ('surfaces', 'heat', 'restrictions'):
            spec = planning.get(role)
            if spec and (not isinstance(spec, dict) or not spec.get('class_field') or not isinstance(spec.get('mapping'), dict) or not spec['mapping']):
                errors.append(f'planning.{role}: select a category field and supply an explicit value mapping.')
            elif spec:
                allowed = {'roof', 'open_space', 'verge', 'pavement', 'parking', 'footway', 'unknown'} if role == 'surfaces' else {'priority', 'other', 'unknown'} if role == 'heat' else {'infiltration_excluded', 'unknown'}
                if any(not isinstance(value, str) or value not in allowed for value in spec['mapping'].values()):
                    errors.append(f'planning.{role}: unsupported mapped category.')
    if config.get('mode') == 'planning' and config.get('combinations'):
        errors.append('Planning mode exports concept options; registered physical combinations require engineering mode.')
    for key in ('run_id', 'area_label', 'scenario_id', 'groundwater_scenario_id', 'output_dir'):
        if not isinstance(config.get(key), str) or not config[key].strip():
            errors.append(f'{key}: enter a nonempty value.')
    if config.get('scenario_id') in ('UNKNOWN', 'REQUIRED'):
        errors.append('scenario_id: register the actual provider event/scenario identifier.')
    if config.get('stated_return_period_years') is not None:
        from .engine import number
        period = number(config['stated_return_period_years'])
        if period is None or period <= 0:
            errors.append('stated_return_period_years: use a positive finite value from event metadata, or null when unknown.')
    if not isinstance(config.get('crs'),str) or not config['crs'].strip():
        errors.append('crs: select a projected processing CRS in metres for this study area.')
    try:
        intervention_need(0, config.get('flood_threshold_m'))
        policy = validate_policy(config.get('policy') or {})
        jurisdiction = config.get('jurisdiction',policy['municipality'])
        if not isinstance(jurisdiction,str):
            errors.append('jurisdiction: enter the governing rule area as text.')
        elif policy['rule_scope'] and place_key(jurisdiction) != place_key(policy['rule_scope']):
            errors.append('The study jurisdiction does not match the selected rule profile. Choose a local profile or generic planning rules.')
    except (ValueError, TypeError) as exc:
        errors.append(str(exc))
    maximum = config.get('max_units', 250000)
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
        errors.append('max_units: enter a positive integer.')
    designs = config.get('designs', list(DESIGNS))
    if not isinstance(designs, list) or not designs or any(d not in DESIGNS for d in designs if isinstance(d, str)) or any(not isinstance(d, str) for d in designs):
        errors.append('designs: select at least one valid NbS design.')
    elif len(set(designs)) != len(designs):
        errors.append('designs: remove duplicate selections.')
    for key in ('evidence', 'raster_evidence', 'distance_evidence', 'derived_module_bases', 'combinations'):
        if not isinstance(config.get(key, []), list) or any(not isinstance(s, dict) for s in config.get(key, [])):
            errors.append(f'{key}: expected a list of objects.')
    for key in ('flood', 'study_area'):
        if not isinstance(config.get(key), dict) or not config[key].get('path'):
            errors.append(f'{key}: select a saved input file.')
    flood = config.get('flood') or {}
    if isinstance(flood, dict):
        if flood.get('type') not in ('raster', 'vector'):
            errors.append('flood.type: select raster or vector.')
        if flood.get('units') not in ('cm', 'm'):
            errors.append('flood.units: select centimetres (cm) or metres (m).')
        if flood.get('type') == 'vector' and not flood.get('depth_field'):
            errors.append('flood.depth_field: select the numeric depth field.')
    m = config.get('muriel') or {}
    if not isinstance(m, dict):
        errors.append('muriel: expected an object.')
    else:
        if 'enabled' in m and not isinstance(m['enabled'], bool):
            errors.append('muriel.enabled: use true or false, not text.')
        if not isinstance(m.get('receptors', []), list) or any(not isinstance(s, dict) for s in m.get('receptors', [])):
            errors.append('muriel.receptors: expected a list of layer specifications.')
        try:
            muriel_settings(m.get('thresholds'))
        except (ValueError, TypeError) as exc:
            errors.append(str(exc))
        for key in ('criteria_scope','criteria_adoption_ref','criteria_profile_id'):
            if m.get(key) is not None and not isinstance(m[key],str):
                errors.append(f'muriel.{key}: use text or null.')
        source = m.get('criteria_source')
        if source is not None and (not isinstance(source,dict) or any(not isinstance(source.get(k),str) or not source[k].strip() for k in ('citation','locator','status'))):
            errors.append('muriel.criteria_source: provide citation, locator and verification status.')
    # Do not traverse malformed containers while gathering further errors.
    if not errors:
        for role, spec in input_specs(config):
            if not isinstance(spec, dict) or not isinstance(spec.get('path'), str) or not spec['path'].strip():
                errors.append(f'{role}: select a saved input file.')
    preparation=config.get('preparation') or {}
    if not isinstance(preparation,dict):errors.append('preparation: expected an object.')
    elif 'enabled' in preparation and not isinstance(preparation['enabled'],bool):errors.append('preparation.enabled: use true or false.')
    offset=config.get('unit_id_grid_offset',[0,0])
    if not isinstance(offset,list) or len(offset)!=2 or any(isinstance(v,bool) or not isinstance(v,int) for v in offset):errors.append('unit_id_grid_offset: expected two integer source-grid offsets.')
    return errors


def resolve_config(source, base_dir=None):
    config = load_data(source)
    errors = structure_errors(config)
    if errors:
        raise ValueError('\n'.join(errors))
    base = Path(base_dir or (Path(source).resolve().parent if not isinstance(source, dict) else Path.cwd()))
    config['policy'] = validate_policy(config.get('policy') or {})
    config.setdefault('jurisdiction',config['policy']['municipality'])
    m = config.get('muriel') or {}
    if m.get('enabled'):
        settings = muriel_settings(m.get('thresholds'))
        changed = any(settings[key] != value for key,value in MURIEL_DEFAULTS.items())
        m.setdefault('criteria_profile_id','adapted_unregistered' if changed else 'porz_eil_2022_reference')
        m.setdefault('criteria_scope',config['jurisdiction'])
        m.setdefault('criteria_adoption_ref',None)
        m.setdefault('criteria_source', {'citation':'Locally adapted MURIEL criteria; source registration outstanding',
                                       'locator':'Resolved configuration muriel.thresholds', 'url':'', 'status':'unregistered_local_criteria'} if changed else deepcopy(SOURCES['MURIEL']))
        m['criteria_source'].setdefault('url','')
        m['criteria_scope_matches'] = bool(m['criteria_scope']) and place_key(m['criteria_scope']) == place_key(config['jurisdiction'])
        config['muriel'] = m
    config['designs'] = config.get('designs', list(DESIGNS))
    for _, spec in input_specs(config):
        spec['path'] = str((base / spec['path']).resolve())
    config['output_dir'] = str((base / config['output_dir']).resolve())
    if (config.get('preparation') or {}).get('output_dir'):
        config['preparation']['output_dir']=str((base/config['preparation']['output_dir']).resolve())
    return config


def starter_config(flood=None, study_area=None, output_dir='results', area_label='Study area', scenario='REQUIRED', threshold_cm=10,
                   crs='', jurisdiction='', profile='generic'):
    """No invented evidence or approvals in a new project."""
    policy = profile_template(profile)
    if jurisdiction:
        policy['municipality'] = jurisdiction
    return {'schema_version':'0.6', 'run_id': 'STUDY_RUN_001', 'area_label': area_label, 'scenario_id': scenario,
            'scenario_description': 'Confirm the event definition against provider metadata.',
            'stated_return_period_years': None, 'return_period_source': None,
            'groundwater_scenario_id': 'UNKNOWN_DESIGN_GROUNDWATER', 'vertical_datum': None,
            'crs': crs, 'jurisdiction':jurisdiction or policy['municipality'], 'flood_threshold_m': float(threshold_cm) / 100,
            'flood_threshold_reference':'Project planning assumption; default 10 cm retained from original user specification; review for this area.',
            'max_units': 250000, 'flood': flood or {'path': '', 'type': 'raster', 'units': None, 'band': 1},
            'study_area': study_area or {'path': ''}, 'output_dir': str(output_dir),
            'policy': policy, 'designs': list(DESIGNS),
            'evidence': [], 'raster_evidence': [], 'distance_evidence': [],
            'derived_module_bases': [], 'combinations': [], 'ownership': None,
            'muriel': {'enabled': False, 'criteria_profile_id':'porz_eil_2022_reference', 'criteria_scope':jurisdiction or policy['municipality'],
                       'criteria_adoption_ref':None, 'receptors': [], 'municipal_land': None,
                       'roads': None, 'usable_space': None, 'routes': None}}


def planning_config(**kwargs):
    """Two required spatial inputs; detailed design proof is collected later."""
    config = starter_config(**kwargs)
    config.update(mode='planning', planning={'surfaces': None, 'heat': None, 'restrictions': None})
    config['muriel']['enabled'] = False
    return config
