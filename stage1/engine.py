"""Pure decision logic; explicit unknowns and a complete rule-by-rule audit."""

from dataclasses import asdict, dataclass
import math
from .catalogue import DEFAULT_POLICY, DESIGNS, SOURCES

STATUSES = ("ADMISSIBLE", "CONDITIONAL", "FAIL", "NOT_APPLICABLE")

MURIEL_DEFAULTS = {
    'footprint_mode': 'depth_mask',
    'flood_extent_depth_m': 0.0, 'min_area_m2': 2000.0,
    'min_max_depth_m': 0.30, 'receptor_distance_m': 1.0,
    'municipal_distance_m': 50.0, 'destination_distance_m': 100.0,
    'protect_overlap_fraction': 0.70,
}


def muriel_settings(overrides=None):
    settings = {**MURIEL_DEFAULTS, **(overrides or {})}
    for key in MURIEL_DEFAULTS:
        if key == 'footprint_mode':
            continue
        value = number(settings[key])
        if value is None or value < 0:
            raise ValueError(f'Invalid MURIEL threshold: {key}')
        settings[key] = value
    if settings['footprint_mode'] not in ('depth_mask', 'inundation_maximum'):
        raise ValueError('MURIEL footprint_mode must be depth_mask or inundation_maximum')
    if settings['protect_overlap_fraction'] > 1:
        raise ValueError('MURIEL overlap fraction must be in [0,1]')
    if settings['flood_extent_depth_m'] > settings['min_max_depth_m']:
        raise ValueError('MURIEL extent threshold cannot exceed the hotspot maximum-depth criterion')
    return settings


@dataclass
class Decision:
    rule_id: str
    status: str
    reason: str
    observed: str
    expected: str
    source_id: str
    evidence_ref: str
    responsible_party: str
    closure: str

    def record(self):
        return {**asdict(self), **{"citation": SOURCES[self.source_id]["citation"],
                                "source_url": SOURCES[self.source_id]["url"],
                                "source_locator": SOURCES[self.source_id]["locator"]}}


def aggregate(decisions):
    statuses = [d.status for d in decisions if d.status != "NOT_APPLICABLE"]
    if "FAIL" in statuses:
        return "FAIL"
    if not statuses or "CONDITIONAL" in statuses:
        return "CONDITIONAL"
    return "ADMISSIBLE"


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def truth(value):
    if value in (True, 1, "true", "TRUE", "yes"):
        return True
    if value in (False, 0, "false", "FALSE", "no"):
        return False
    return None


def validate_policy(policy):
    p = {**DEFAULT_POLICY, **policy}
    if not isinstance(p['profile_reviewed'], bool):
        raise ValueError('profile_reviewed must be a JSON boolean, never a string')
    if p["municipality"] != p["rule_scope"] and not (p["profile_reviewed"] and p["profile_review_ref"]):
        raise ValueError("A different NRW municipality needs a reviewed local rule profile and reference; Cologne rules cannot be silently transferred.")
    for key in ("groundwater_floor_m", "groundwater_preferred_m", "neighbour_setback_m", "basement_recommended_m", "asset_clearance_m"):
        numeric = number(p[key])
        if numeric is None or numeric < 0:
            raise ValueError(f"Invalid nonnegative policy threshold: {key}")
        p[key] = numeric
    if p["groundwater_floor_m"] > p["groundwater_preferred_m"]:
        raise ValueError("Groundwater floor must not exceed preferred clearance")
    return p


class Rules:
    def __init__(self, attrs, policy, design=None):
        self.a, self.p, self.design = attrs, validate_policy(policy), design
        self.rows = []

    def value(self, key):
        # Design-specific proof overrides general evidence. Base elevations ONLY
        # use a specific design key, never a common guessed depth for every NbS.
        if self.design and f"{key}__{self.design}" in self.a:
            return self.a[f"{key}__{self.design}"]
        return self.a.get(key)

    def add(self, rid, status, reason, observed=None, expected="", source="THESIS", closure="", party="Site designer / evidence owner"):
        evidence = self.a.get(f"evidence_ref__{rid}") or self.a.get("evidence_ref") or "MISSING"
        self.rows.append(Decision(rid, status, reason, str(observed), expected, source, str(evidence), party,
                                  closure if status in ("CONDITIONAL", "FAIL") else "None for this screening rule"))

    def boolean(self, key, label, source="THESIS", on_false="FAIL", party="Site designer / evidence owner"):
        raw = self.value(key)
        v = truth(raw)
        self.add(key, "CONDITIONAL" if v is None else "ADMISSIBLE" if v else on_false,
                 label + (": evidenced" if v else ": incompatible / unresolved" if v is False else ": evidence missing or mixed"),
                 raw, "Documented true", source,
                 f"Provide a dated, referenced assessment of {label.lower()}; redesign if incompatible.", party)

    def minimum(self, key, limit, label, source, recommended=False):
        value = number(self.value(key))
        status = "CONDITIONAL" if value is None else "ADMISSIBLE" if value >= limit else "CONDITIONAL" if recommended else "FAIL"
        self.add(key, status, label, value, f"≥ {limit:g} m" + (" (recommendation)" if recommended else ""), source,
                 "Survey the proposed module footprint and obtain authority / specialist review; redesign where necessary.")

    def profile(self):
        ok = self.p["profile_reviewed"] and bool(self.p["profile_review_ref"])
        self.add("local_rule_profile", "ADMISSIBLE" if ok else "CONDITIONAL",
                 "Local rules and authority scope reviewed" if ok else "Document-derived profile has not been validated against current primary sources and local authority requirements",
                 self.p["profile_review_ref"], f"Reviewed rules for {self.p['municipality']}", "THESIS",
                 "Confirm current primary guidance, applicable plan / permit and local authority conditions; record the review reference.", "Researcher / competent authority")
        self.add("evidence_traceability", "ADMISSIBLE" if self.a.get("evidence_ref") else "CONDITIONAL",
                 "Referenced site evidence" if self.a.get("evidence_ref") else "No site evidence reference supplied",
                 self.a.get("evidence_ref"), "Dated evidence register reference", "THESIS",
                 "Link every supplied value to dated site evidence; field-level evidence_ref__<rule_id> is supported.")


def intervention_need(depth, threshold_m=0.10):
    threshold = number(threshold_m)
    if threshold is None or threshold < 0:
        raise ValueError("Flood threshold must be finite and nonnegative, in metres")
    d = number(depth)
    if d is None or d < 0:
        return "UNKNOWN"
    return "YES" if d >= threshold else "NO"


def groundwater(attrs, policy, design=None, vertical_datum=None, groundwater_scenario_id=None):
    r = Rules(attrs, policy, design)
    r.profile()
    zone = str(r.value("protection_zone") or "UNKNOWN").upper().replace(" ", "")
    if zone in ("I", "II"):
        r.add("protection_zone", "FAIL", "Infiltration normally excluded in protection zones I–II", zone, "Outside I–II", "KOELN2022", "Use a separately assessed non-infiltrating design.")
    elif zone in ("III", "IIIA", "IIIB"):
        if design == "infiltration_shaft":
            r.add("protection_zone", "FAIL", "Shaft route in thesis is limited to outside protection zones", zone, "Outside water-protection zones", "KOELN2022", "Redesign the pathway and confirm the current authority requirements.")
        else:
            r.boolean("outer_zone_authority_ok", "Outer-zone typology and authority exception / conditions confirmed", "KOELN2022", "CONDITIONAL", "Water authority")
    elif zone == "OUTSIDE":
        r.add("protection_zone", "ADMISSIBLE", "Outside mapped water-protection zones", zone, "Known zone status", "KOELN2022")
    else:
        r.add("protection_zone", "CONDITIONAL", "Protection-zone evidence missing or unrecognized", zone, "I / II / III / IIIA / IIIB / OUTSIDE", "KOELN2022", "Obtain current authoritative water-protection boundaries.")
    for key, label in [("receiving_ground_clean", "Clean receiving ground / contamination resolved"),
                       ("soil_infiltration_ok", "Site-scale soil and infiltration suitability"),
                       ("runoff_quality_ok", "Runoff quality and treatment acceptable for infiltration")]:
        r.boolean(key, label, "KOELN2022")
    r.boolean("aquifer_evidence_ok", "Aquifer setting and groundwater fluctuation evidence", on_false="CONDITIONAL")
    r.boolean("mounding_assessed_ok", "Groundwater mounding / neighbouring receptors assessed", "DWA_SUMMARY", "CONDITIONAL")
    r.minimum("neighbour_distance_m", r.p["neighbour_setback_m"], "Distance to neighbouring property", "KOELN2022")
    basement = truth(r.value("non_waterproof_basement_present"))
    if basement is False:
        r.add("basement_distance_m", "NOT_APPLICABLE", "Evidence confirms no relevant non-waterproof basement", False, "Documented basement condition", "KOELN2022")
    elif basement is True:
        r.minimum("basement_distance_m", r.p["basement_recommended_m"], "Recommended non-waterproof basement separation", "KOELN2022", recommended=True)
    else:
        r.add("basement_distance_m", "CONDITIONAL", "Basement presence / waterproofing unknown", None, "Documented basement status", "KOELN2022", "Survey relevant basements and foundation protections.")

    # A groundwater-depth raster alone cannot establish module-base clearance.
    base = number(attrs.get(f"module_base_elevation_m__{design}")) if design else None
    gw = number(r.value("design_groundwater_elevation_m"))
    uncertainty = number(r.value("groundwater_uncertainty_m"))
    datum_ok = bool(vertical_datum) and r.value("vertical_datum") == vertical_datum
    state_ok = bool(groundwater_scenario_id) and r.value("groundwater_scenario_id") == groundwater_scenario_id
    if not design:
        r.add("groundwater_clearance", "CONDITIONAL", "Preliminary groundwater pathway screen; no specific module-base design", None,
              "Design-specific module base, design groundwater state and uncertainty on a common vertical datum", "DWA_SUMMARY",
              "Define each module base and re-evaluate final clearance. A coarse screen never establishes final infiltration permission.")
    elif base is None or gw is None or uncertainty is None or uncertainty < 0 or not datum_ok or not state_ok:
        r.add("groundwater_clearance", "CONDITIONAL", "Module base, design groundwater, uncertainty, scenario or common vertical datum missing / incompatible",
              {"base_m": base, "groundwater_m": gw, "uncertainty_m": uncertainty, "datum_matches": datum_ok, "scenario_matches": state_ok},
              "base elevation − design groundwater elevation − uncertainty", "DWA_SUMMARY",
              "Survey design-specific base elevations; document MHGW / design state, datum and nonnegative uncertainty.")
    else:
        clearance = base - gw - uncertainty
        preferred, floor = r.p["groundwater_preferred_m"], r.p["groundwater_floor_m"]
        # Elevation subtraction can introduce floating-point error at an exact
        # boundary. Normalize only sub-nanometre arithmetic differences.
        for boundary in (floor, preferred):
            if math.isclose(clearance, boundary, rel_tol=0, abs_tol=1e-9):
                clearance = boundary
        if clearance < floor:
            status, reason = "FAIL", "Robust module-base separation below the provisional technical-summary floor"
        elif clearance < preferred:
            ok = truth(r.value("low_pollution_runoff")) is True and truth(r.value("groundwater_exception_approved")) is True and truth(r.value("groundwater_standard_confirmed")) is True
            status = "ADMISSIBLE" if ok else "CONDITIONAL"
            reason = "Exceptional separation band: low-pollution runoff, confirmed standard and explicit authority exception required"
        else:
            status = "ADMISSIBLE" if truth(r.value("groundwater_standard_confirmed")) is True else "CONDITIONAL"
            reason = "Preferred separation met; primary-standard and authority applicability must be confirmed"
        r.add("groundwater_clearance", status, reason,
              f"{clearance:.6g} m = {base:g} − {gw:g} − {uncertainty:g}",
              f"Preferred ≥{preferred:g} m; [{floor:g}, {preferred:g}) m exception; <{floor:g} m fail (secondary summary)",
              "DWA_SUMMARY", "Confirm DWA-A 138-1 and authority conditions; close exceptions or assess a separately encoded lined design.", "Hydrogeologist / water authority")
    return r.rows


COMMON_RULES = [
    ("functional_need_ok", "Connection to documented flood need or runoff source", "FAIL"),
    ("source_pathway_ok", "Source → inlet → function → outlet represented", "FAIL"),
    ("safe_overflow_ok", "Safe overflow and no unacceptable receptor transfer", "FAIL"),
    ("land_control_ok", "Land rights / owner agreement", "CONDITIONAL"),
    ("access_ok", "Construction and maintenance access", "CONDITIONAL"),
    ("maintenance_assigned", "Named maintenance owner and plan", "CONDITIONAL"),
    ("construction_feasible", "Construction and normal use compatible", "FAIL"),
    ("planning_compatible", "Applicable development plan and property controls compatible", "FAIL"),
    ("design_geometry_confirmed", "Specific intervention geometry / footprint confirmed", "CONDITIONAL"),
]


def evaluate_design(attrs, design, policy, vertical_datum=None, groundwater_scenario_id=None):
    if design not in DESIGNS:
        raise ValueError(f"Unknown design {design}")
    label, family, infiltrates, land_types = DESIGNS[design]
    r = Rules(attrs, policy, design)
    r.profile()
    land = r.value("land_type")
    r.add("land_type", "CONDITIONAL" if land is None else "ADMISSIBLE" if land in land_types else "FAIL",
          f"{label}: compatible surface / footprint", land, ", ".join(land_types), "THESIS",
          "Check actual intervention geometry and surface type; split mixed analysis units.")
    for key, text, on_false in COMMON_RULES:
        r.boolean(key, text, on_false=on_false)
    approval = r.value("permission_status")
    status = "ADMISSIBLE" if approval in ("confirmed", "not_required_confirmed") else "FAIL" if approval == "refused" else "CONDITIONAL"
    r.add("permission_status", status, "Pathway-specific permit / notification and authority route", approval,
          "confirmed or not_required_confirmed; pending / missing conditional; refused fail", "KOELN2022" if infiltrates else "THESIS",
          "Record competent authority, required route, decision / notification reference and applicable conditions.", "Owner / competent authority")

    if family == "roof":
        for key in ("roof_structure_ok", "roof_waterproofing_ok", "roof_drainage_ok", "roof_fire_safety_ok"):
            r.boolean(key, key.replace("_", " "), "ROOF2026")
        pv = truth(r.value("pv_present"))
        if pv is True:
            r.boolean("roof_pv_compatibility_ok", "PV / substrate clearance and roof design compatible", "ROOF2026")
        elif pv is False:
            r.add("roof_pv_compatibility_ok", "NOT_APPLICABLE", "No PV installation evidenced", False, "PV condition known", "ROOF2026")
        else:
            r.add("roof_pv_compatibility_ok", "CONDITIONAL", "PV presence unknown", None, "PV evidence", "ROOF2026", "Check PV and roof layout.")
        if design == "blue_green_roof":
            r.boolean("roof_retention_design_ok", "Blue-green storage, throttle and emergency drainage design", "ROOF2026")
        r.add("groundwater_pathway", "NOT_APPLICABLE", "Roof design contains no deliberate infiltration", None, "Separate downstream modules assessed independently", "THESIS")
    else:
        for key in ("utilities_clearance_ok", "excavation_contamination_ok", "drainage_asset_access_ok"):
            r.boolean(key, key.replace("_", " "), "STEB2025" if "asset" in key else "THESIS")
        assets = truth(r.value("public_drainage_assets_present"))
        if assets is True:
            r.minimum("asset_edge_distance_m", r.p["asset_clearance_m"], "Clearance from public drainage asset edge", "STEB2025")
            diameter, distance = number(r.value("sewer_profile_cm")), number(r.value("sewer_centerline_distance_m"))
            width = None if diameter is None or diameter < 0 else 10.0 if diameter >= 200 else 7.5 if diameter >= 70 else 6.0
            coordinated = truth(r.value("sewer_strip_coordination_ok")) is True
            ok = width is not None and distance is not None and distance >= width / 2
            r.add("sewer_protection_strip", "ADMISSIBLE" if ok or coordinated else "CONDITIONAL",
                  "Sewer protection corridor: total width 6 / 7.5 / 10 m; early StEB coordination for affected works",
                  {"profile_cm": diameter, "centerline_distance_m": distance, "strip_total_width_m": width, "agreement": coordinated},
                  "Outside mapped protection strip or documented agreement; widths assumed centred, verify actual asset corridor", "STEB2025",
                  "Use authorized surveyed protection-corridor geometry and obtain StEB conditions; never infer edge distance from pipe centreline.")
        elif assets is False:
            r.add("drainage_asset_clearance", "NOT_APPLICABLE", "Authorized evidence confirms no affected public drainage assets", False, "Verified asset coverage", "STEB2025")
        else:
            r.add("drainage_asset_clearance", "CONDITIONAL", "Public drainage-asset evidence incomplete", None, "Authorized asset evidence", "STEB2025", "Obtain authorized asset / corridor data and check access and clearance.")
        if infiltrates:
            # Keep each source row only once, retaining a separate profile audit above.
            r.rows.extend(d for d in groundwater(attrs, policy, design, vertical_datum, groundwater_scenario_id)
                          if d.rule_id not in ("local_rule_profile", "evidence_traceability"))
        else:
            if family == 'conveyance':
                r.boolean('no_deliberate_infiltration_ok', 'Surface route has no deliberate infiltration; seepage and water quality addressed')
            else:
                r.boolean("lining_integrity_ok", "No deliberate infiltration: lining and controlled destination evidenced")
            r.boolean("outlet_capacity_ok", "Controlled outlet / receiving destination capacity")
            r.add("groundwater_infiltration_rules", "NOT_APPLICABLE", "This variant has no deliberate infiltration; excavation and structural groundwater risks remain applicable", None, "Distinct lined / controlled-release design", "THESIS")
            r.boolean("groundwater_structural_risk_ok", "Groundwater uplift / excavation / structural risks assessed")
        specific = {
            "surface": ["living_soil_treatment_ok"],
            "swale": ["slope_erosion_ponding_ok"],
            "rain_garden": ["media_vegetation_treatment_ok"],
            "tree": ["rootable_soil_volume_ok", "tree_root_utility_conflict_resolved", "tree_and_drainage_maintenance_ok"],
            "pavement": ["pavement_loading_ok", "subbase_storage_ok", "declogging_plan_ok"],
            "trench": ["pretreatment_ok", "inspection_cleaning_ok"],
            "swale_trench": ["slope_erosion_ponding_ok", "pretreatment_ok", "inspection_cleaning_ok", "combined_system_layout_ok"],
            "shaft": ["pretreatment_ok", "inspection_cleaning_ok", "shaft_hydrogeology_ok"],
            "detention": ["normal_use_safety_ok", "retention_function_protected"],
            "conveyance": ["route_rights_ok", "downstream_receptors_ok"],
        }
        for key in specific[family]:
            r.boolean(key, key.replace("_", " "))
    return r.rows


def evaluate_combination(combination, evaluations, units):
    """Check a declared portfolio, without summing hydraulic benefits.

    Areas and capacities are allocations, not performance estimates. Shared-source
    allocations are fractions of a named source; a source may not be counted twice.
    """
    r = Rules({"evidence_ref": combination.get("evidence_ref")}, {})
    r.add('combination_evidence_traceability', 'ADMISSIBLE' if combination.get('evidence_ref') else 'CONDITIONAL',
          'Combined-system evidence register reference', combination.get('evidence_ref'), 'Dated combination-specific evidence reference',
          closure='Link the combined layout, route and accounting verification to dated evidence.')
    modules = combination.get("modules", [])
    if len(modules) < 2:
        r.add("combination_members", "FAIL", "A combination requires at least two modules", len(modules), "≥2 modules", closure="Declare at least two modules.")
    seen, footprints, allocated, source_fraction = set(), set(), {}, {}
    module_ids = []
    for i, module in enumerate(modules):
        key = (str(module.get("unit_id")), module.get("design"))
        if key not in evaluations:
            raise ValueError(f"Combination {combination.get('id')} references unknown module {key}")
        rows = evaluations[key]
        state = aggregate(rows)
        detail = "; ".join(f"{d.rule_id}: {d.reason}" for d in rows if d.status in ("FAIL", "CONDITIONAL"))
        r.add(f"member_{i+1}", state, f"{key[0]} / {key[1]}: {detail or 'all screening gates satisfied'}", state,
              "Every member admissible; conditional branches remain separate", closure="Close member-specific conditions or redesign; no benefit can offset a failed member.")
        if key in seen:
            r.add("duplicate_module", "FAIL", "Same unit-design module included twice", key, "Unique modules", closure="Remove duplicate module.")
        seen.add(key)
        mid = module.get('module_id')
        if not mid or mid in module_ids:
            r.add(f'module_identifier_{i+1}', 'FAIL', 'Each module needs a unique nonempty module_id', mid, 'Unique module_id', closure='Assign stable module IDs for hydraulic links.')
        module_ids.append(mid)
        footprint = module.get('footprint_id')
        if not footprint:
            r.add(f'footprint_identifier_{i+1}', 'CONDITIONAL', 'No distinct design footprint recorded', None, 'Surveyed footprint_id', closure='Register each module footprint and verify layout.')
        elif footprint in footprints:
            r.add('overlapping_footprint', 'FAIL', 'Two module designs claim the same footprint', footprint, 'Disjoint footprints or one explicitly redesigned combined module', closure='Separate the footprints or encode a single integrated design.')
        footprints.add(footprint)
        area = number(module.get("allocated_area_m2"))
        if area is None or area <= 0:
            r.add(f"footprint_{i+1}", "CONDITIONAL" if area is None else "FAIL", "Positive module footprint allocation required", area, ">0 m²", closure="Provide a surveyed, disjoint module footprint.")
        else:
            allocated[key[0]] = allocated.get(key[0], 0.0) + area
        sid, fraction = module.get("source_id"), number(module.get("source_fraction"))
        if not sid or fraction is None:
            r.add(f"source_allocation_{i+1}", "CONDITIONAL", "Source allocation missing", module.get("source_id"), "Named source and routed fraction", closure="Allocate each source once; explicitly account for serial treatment routing.")
        elif fraction < 0 or fraction > 1:
            r.add(f"source_allocation_{i+1}", "FAIL", "Source fraction outside [0,1]", fraction, "0 ≤ fraction ≤ 1", closure="Correct source accounting.")
        else:
            source_fraction[sid] = source_fraction.get(sid, 0.0) + fraction
    for uid, area in allocated.items():
        capacity = units[uid]["area_m2"]
        r.add(f"space_budget_{uid}", "ADMISSIBLE" if area <= capacity + 1e-7 else "FAIL", "Allocated footprints versus available unit area (necessary, not sufficient for layout)",
              area, f"≤{capacity:g} m²", closure="Reduce allocations or change site; verify disjoint footprints and 3D placement.")
    for source, fraction in source_fraction.items():
        r.add(f"source_budget_{source}", "ADMISSIBLE" if fraction <= 1 + 1e-9 else "FAIL", "No duplicate source-area credit", fraction, "Total allocated source fraction ≤1", closure="Use incremental source allocations; encode serial transfers separately and verify water accounting.")
    links = combination.get('links', [])
    if not links:
        r.add('hydraulic_link_graph', 'CONDITIONAL', 'No explicit source-module to destination-module links', None, 'Directed module links, with pathway evidence', closure='Register hydraulic links; adjacency alone is insufficient.')
    else:
        adjacency = {m: set() for m in module_ids}
        valid = True
        for link in links:
            origin, destination = link.get('from'), link.get('to')
            if origin not in adjacency or destination not in adjacency or origin == destination:
                valid = False
            else:
                adjacency[origin].add(destination)
                adjacency[destination].add(origin)
        visited, pending = set(), [module_ids[0]] if module_ids else []
        while pending:
            node = pending.pop()
            if node not in visited:
                visited.add(node)
                pending.extend(adjacency.get(node, set()) - visited)
        connected = valid and len(visited) == len(adjacency)
        r.add('hydraulic_link_graph', 'ADMISSIBLE' if connected else 'FAIL', 'Explicit module links form a connected system' if connected else 'Unknown endpoint, self-link or disconnected module in combination', links, 'All modules connected through declared valid links', closure='Correct the declared system and obtain hydraulic route evidence.')
    for store in combination.get('shared_storage', []):
        capacity = number(store.get('capacity_m3'))
        allocations = [number(v) for v in store.get('allocations_m3', [])]
        valid = capacity is not None and capacity >= 0 and bool(allocations) and all(v is not None and v >= 0 for v in allocations)
        state = 'CONDITIONAL' if not valid else 'ADMISSIBLE' if sum(allocations) <= capacity + 1e-9 else 'FAIL'
        r.add('shared_storage_' + str(store.get('id', 'UNKNOWN')), state, 'Shared storage allocation does not create extra capacity', store, 'Nonnegative allocations summing to ≤ declared physical capacity', closure='Register the shared capacity once and correct allocations.')
    r.a.update(combination)
    for key in ("layout_verified", "hydraulic_link_verified", "shared_source_accounting_verified", "shared_storage_accounting_verified", "outlet_capacity_verified", "ownership_operation_verified"):
        r.boolean(key, key.replace("_", " "), on_false="CONDITIONAL")
    r.add("screening_scope", "ADMISSIBLE", "Spatial compatibility only; no flood reduction or additive hydraulic benefit inferred", "Stage 1", "Stage 2 direct hydraulic simulation required", "THESIS")
    return r.rows


def evaluate_muriel(metrics, settings=None):
    """Local planning screen from thesis §§4.4.2/5.5.3, not an NbS permit.

    The default footprint dissolves cells deeper than 0.30 m, as labelled in
    Schwerdorf slides 19–20. inundation_maximum is an explicit alternative
    reflecting the thesis §5.5.3 maximum-depth wording.
    """
    p = muriel_settings(settings)
    r = Rules({'evidence_ref': metrics.get('evidence_ref')}, {})
    reference = metrics.get('evidence_ref')
    r.add('MURIEL_SOURCE_TRACEABILITY', 'ADMISSIBLE' if reference and 'MISSING' not in str(reference) else 'CONDITIONAL',
          'Traceable source inventories for this screen', reference, 'Dated source inventory / evidence-register references', 'THESIS',
          'Provide the source inventory references; file checksums are retained separately in input_provenance.')
    r.add('MURIEL_FOOTPRINT_DEFINITION', 'ADMISSIBLE', 'Registered flood-footprint interpretation',
          p['footprint_mode'], 'depth_mask: cells > depth criterion; inundation_maximum: wet extent plus separate maximum-depth test',
          'MURIEL' if p['footprint_mode'] == 'depth_mask' else 'THESIS')
    incomplete = bool(metrics.get('boundary_incomplete'))
    area, depth = number(metrics.get('area_m2')), number(metrics.get('max_depth_m'))
    for rid, value, threshold, unit in [
        ('MURIEL_AREA', area, p['min_area_m2'], 'm²'),
        ('MURIEL_MAX_DEPTH', depth, p['min_max_depth_m'], 'm'),
    ]:
        status = 'CONDITIONAL' if value is None else 'ADMISSIBLE' if value > threshold else 'CONDITIONAL' if incomplete else 'FAIL'
        r.add(rid, status, 'Connected flood-polygon ' + ('area' if rid.endswith('AREA') else 'maximum depth'),
              value, f'> {threshold:g} {unit} (strict)', 'MURIEL',
              'Check source flood extent, depth units and scenario; retain polygons below the screen in the audit.')
    r.add('MURIEL_EXTENT_EVIDENCE', 'CONDITIONAL' if incomplete else 'ADMISSIBLE',
          'Flood footprint touches the analysis boundary or adjacent NoData' if incomplete else 'Observed footprint is interior and not adjacent to flood NoData',
          metrics.get('extent_note'), 'Untruncated flood extent and known adjacent depth coverage', 'THESIS',
          'Extend the source/analysis domain or resolve NoData before treating the observed area as the full hotspot.')
    for key, limit_key, strict in [
        ('receptor', 'receptor_distance_m', True),
        ('municipal', 'municipal_distance_m', True),
        ('destination', 'destination_distance_m', False),
    ]:
        distance = number(metrics.get(key + '_distance_m'))
        complete = metrics.get(key + '_coverage_complete') is True
        limit = p[limit_key]
        within = distance is not None and (distance < limit if strict else distance <= limit)
        state = 'ADMISSIBLE' if within else 'FAIL' if complete and not incomplete else 'CONDITIONAL'
        r.add('MURIEL_' + key.upper(), state,
              {'receptor': 'Building or sensitive-object adjacency', 'municipal': 'Verified non-road municipal land availability', 'destination': 'Verified usable municipal destination space'}[key],
              {'distance_m': distance, 'inventory_complete': complete},
              f'{"<" if strict else "≤"} {limit:g} m; polygon-edge distance', 'MURIEL',
              'Obtain complete source coverage and confirm the relevant inventory / ownership / non-road / usability classification.')
    overlap = number(metrics.get('overlap_fraction'))
    protected = overlap is not None and overlap >= p['protect_overlap_fraction']
    overlap_known = metrics.get('overlap_coverage_complete') is True
    r.add('MURIEL_RETENTION_FUNCTION', 'ADMISSIBLE' if (protected or overlap_known) and not incomplete else 'CONDITIONAL',
          'Observed overlap is provisional because the flood footprint is incomplete' if incomplete else 'Existing retention function to protect' if protected else 'Existing-retention overlap below criterion' if overlap_known else 'Incomplete usable-space evidence cannot rule out an existing retention function',
          overlap, f'≥ {p["protect_overlap_fraction"]*100:g}% verified usable municipal, non-road overlap; union removes duplicates', 'MURIEL',
          'Confirm usable-space coverage and existing retention function; do not designate a protection area as an automatic construction site.')
    lookup = {d.rule_id: d.status for d in r.rows}
    below = 'FAIL' in (lookup['MURIEL_AREA'], lookup['MURIEL_MAX_DEPTH'])
    prior_failure = 'FAIL' in (lookup['MURIEL_RECEPTOR'], lookup['MURIEL_MUNICIPAL'])
    routing_applies = not (below or incomplete or protected or prior_failure or lookup['MURIEL_DESTINATION'] != 'ADMISSIBLE')
    route = metrics.get('best_route_status', 'CONDITIONAL')
    if route not in ('ADMISSIBLE', 'CONDITIONAL', 'FAIL'):
        raise ValueError('Unrecognized MURIEL route status')
    r.add('MURIEL_ROUTING', route if routing_applies else 'NOT_APPLICABLE',
          'Topographic/flow route, downstream safety and land-control evidence for a specific hotspot–destination pair',
          metrics.get('route_note'), 'A nearby polygon or straight proximity line is not proof of safe routing', 'THESIS',
          'Survey and document a specific source–inlet–destination–outlet/exceedance route and its safety/rights; re-evaluate failed routes separately.')
    r.add('MURIEL_GROUNDWATER_CROSSWALK', 'NOT_APPLICABLE',
          'Groundwater screen retained separately; MURIEL does not grant infiltration permission',
          metrics.get('preliminary_infiltration_status', 'CONDITIONAL'), 'Assess actual infiltrating or lined pathway using independent NbS gates', 'THESIS',
          'Retain groundwater/soil/quality restrictions when designing the selected pathway.')
    if incomplete:
        planning = 'EVIDENCE_GAP'
    elif below:
        planning = 'BELOW_SCREEN'
    elif protected:
        planning = 'PROTECT_RETENTION'
    elif prior_failure:
        planning = 'OUTSIDE_PRIORITY'
    elif any(d.status == 'CONDITIONAL' for d in r.rows if d.rule_id != 'MURIEL_ROUTING'):
        planning = 'EVIDENCE_GAP'
    elif lookup['MURIEL_DESTINATION'] == 'FAIL':
        planning = 'NO_DESTINATION'
    else:
        planning = {'ADMISSIBLE': 'RETROFIT_CANDIDATE', 'CONDITIONAL': 'ROUTING_INVESTIGATION', 'FAIL': 'ROUTE_UNSUITABLE'}[route]
    return planning, r.rows
