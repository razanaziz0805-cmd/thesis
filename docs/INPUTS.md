# Stage 1 input specification

## Minimum to produce an actual first map

Supply a **georeferenced SRI5 flood-depth GeoTIFF** and a **study-area polygon** (GeoPackage preferred). The user specifies centimetres and a stated 30-year return period. Preserve the provider's scenario/event documentation, date, resolution, depth-band definition, licence and NoData code. A screenshot or WMS picture alone does not supply numeric depth values per cell. A documented WCS/download or vector depth field can be used instead.

The study boundary must distinguish **Stadtteil Kalk** from the wider **Stadtbezirk Kalk**. Define any contributing-area/hydrological extension separately. Source-control candidates may lie outside the area of high flood depth; a later hydraulic domain must include relevant upstream and downstream connections.

Every `path` in a run JSON is relative to the **JSON file**, unless absolute. Provide `metadata` with provider, version, date, licence/access conditions, source resolution, measurement/model/assumption class, uncertainty and limitations. Files are checksummed. Do not put owner names, personal details or secret credentials in public result bundles.

## Spatial reference and analysis units

- Default horizontal CRS: **EPSG:25832**, ETRS89 / UTM 32N. The workflow requires a projected CRS in metres.
- Vector inputs are explicitly transformed to the processing CRS. Confirm the transformation/datum operation in source preparation for high-accuracy work.
- Flood rasters must already be north-up in the configured CRS. Their cell origin, size and extent are retained. There is no automatic depth interpolation or claim of improved source resolution.
- Document any preprocessing. Use nearest-neighbour for categorical classes; choose and justify an appropriate method for each continuous variable. Interpolating flood depths can move the 10 cm boundary.
- Elevations and distances in evidence fields use **metres**. `vertical_datum` must match the configured datum, e.g. a verified DHHN2016/NHN height system. A CRS label alone does not establish a common vertical reference.
- Raster unit IDs are `r0000000_c0000000` using zero-based source row/column. AOI-edge cells are clipped to the polygon, while retaining the source cell's depth value.
- Vector flood inputs must be valid, nonoverlapping polygons with unique IDs. They can represent a grid or a documented zoning partition. Invalid geometry, missing CRS and duplicate IDs are errors. No silent geometry repairs occur.
- The default cap is 250,000 units. Each unit produces many rule rows; partition a large NRW study, or use a justified polygon/candidate partition, before increasing the cap. This version is not a tiled statewide raster engine.

For polygon flood inputs replace the flood block with:

```json
{"path":"../data/site.gpkg","type":"vector","layer":"flood_grid","id_field":"unit_id","depth_field":"depth_cm","units":"cm","metadata":{"provider":"...","date":"...","version":"...","license":"..."}}
```

## Evidence joins and missing information

An evidence layer is a polygon layer with attributes. An **ID join** uses the analysis `unit_id`; duplicate evidence IDs are rejected. A **spatial join** intersects polygons: a scalar value is accepted only when the entire analysis unit has supporting coverage and consistent values. Mixed/uncovered values become unknown. Protection zones I–II and known contaminated/unsuitable receiving ground are retained conservatively even if they occupy only part of a cell. Distance fields use the minimum; groundwater levels and uncertainty use the maximum; module-base elevations use the minimum. Mixed vertical-datum/scenario labels remain unknown. These are conservative bounds, not invented subcell precision; split analysis units to refine a boundary.

Explicitly map source column names with `fields: {"protection_zone":"zone_class"}`. Evidence may not overwrite analysis IDs, area or flood depth. Later evidence blocks replace their explicitly mapped fields; order them deliberately and record why. Verify coverage and time/state compatibility.

Use **NULL** for absent/unknown evidence. Boolean `true`/1 means documented compatible; `false`/0 means documented incompatible or unresolved as specified in the rule register. Do not fill an unknown register with false, true or zero defaults. A flood raster's NoData is unknown, not a depth of zero. A protection-zone layer that only draws zones does not prove all uncovered areas are outside; supply verified OUTSIDE coverage.

## Groundwater evidence

| Field | Meaning |
|---|---|
| `protection_zone` | `I`, `II`, `III`, `IIIA`, `IIIB`, `OUTSIDE`; null unknown |
| `receiving_ground_clean` | Contamination / contaminated fill investigation resolved for receiving ground |
| `soil_infiltration_ok` | Site-scale soil/permeability assessment supports the design |
| `runoff_quality_ok` | Quality/treatment supports the receiving pathway |
| `aquifer_evidence_ok` | Aquifer setting, fluctuation, design-state evidence adequate |
| `mounding_assessed_ok` | Mounding and neighbouring receptors investigated |
| `design_groundwater_elevation_m` | MHGW or documented design-level elevation; not depth below ground |
| `groundwater_uncertainty_m` | Nonnegative safety/uncertainty allowance, with rationale |
| `groundwater_scenario_id` | Must match the run's registered groundwater state |
| `vertical_datum` | Common verified vertical datum for groundwater and module base |
| `module_base_elevation_m__<design>` | Specific proposed base elevation for that design; required for final clearance |
| `groundwater_standard_confirmed` | Applicability checked against primary standard and authority |
| `low_pollution_runoff`, `groundwater_exception_approved` | Both required, with standard confirmation, in the exceptional separation band |
| `outer_zone_authority_ok` | Typology-specific outer-zone requirements / exception evidenced |
| `neighbour_distance_m` | Minimum horizontal distance **from proposed footprint** to neighbouring property |
| `non_waterproof_basement_present`, `basement_distance_m` | Surveyed relevant basement condition and footprint separation |

A groundwater-depth raster is useful preliminary evidence, but it does not determine the module-base-to-design-groundwater separation. If elevations or the design are absent, the final screen stays conditional. Represent high-groundwater and ordinary states in separate registered runs.

## Common and typology-specific evidence

All designs require `evidence_ref`, `functional_need_ok`, `source_pathway_ok`, `safe_overflow_ok`, `land_control_ok`, `access_ok`, `maintenance_assigned`, `construction_feasible`, `planning_compatible` and `design_geometry_confirmed`.

`permission_status` is `confirmed`, `not_required_confirmed`, `pending`, `refused` or null. Confirmed statuses need a dated decision/notification reference and applicable conditions. Lack of a permit is not the same as a refusal.

Most fields can be overridden per design by appending `__<design>`, e.g. `safe_overflow_ok__tree_trench_lined`. Base elevation is **always** design-specific. Provide a general evidence register reference and, where needed, `evidence_ref__<rule_id>` for individual observations. The layer/metadata must connect that reference to actual records; the software cannot certify the truth of supplied evidence flags.

| Family | Additional evidence fields |
|---|---|
| Roof | `roof_structure_ok`, `roof_waterproofing_ok`, `roof_drainage_ok`, `roof_fire_safety_ok`, `pv_present`; if PV, `roof_pv_compatibility_ok`; retention roof adds `roof_retention_design_ok` |
| All ground works | `utilities_clearance_ok`, `excavation_contamination_ok`, `drainage_asset_access_ok`, `public_drainage_assets_present`; if affected assets, `asset_edge_distance_m`, `sewer_profile_cm`, `sewer_centerline_distance_m`, `sewer_strip_coordination_ok` |
| Lined variants | `lining_integrity_ok`, `outlet_capacity_ok`, `groundwater_structural_risk_ok` |
| Conveyance | `no_deliberate_infiltration_ok`, `outlet_capacity_ok`, `groundwater_structural_risk_ok`, `route_rights_ok`, `downstream_receptors_ok` |
| Living-soil infiltration | `living_soil_treatment_ok` |
| Swale/basin | `slope_erosion_ponding_ok` |
| Rain garden | `media_vegetation_treatment_ok` |
| Tree pit/trench | `rootable_soil_volume_ok`, `tree_root_utility_conflict_resolved`, `tree_and_drainage_maintenance_ok` |
| Permeable pavement | `pavement_loading_ok`, `subbase_storage_ok`, `declogging_plan_ok` |
| Trench | `pretreatment_ok`, `inspection_cleaning_ok` |
| Swale–trench | Swale and trench fields plus `combined_system_layout_ok` |
| Shaft | Trench fields plus `shaft_hydrogeology_ok` |
| Multifunctional detention | `normal_use_safety_ok`, `retention_function_protected` |

Controlled `land_type` values are `roof`, `open_space`, `verge`, `pavement`, `parking`, `footway`. Unknown/mixed units stay conditional; the code catalogue declares each design's accepted types. These are screening assumptions, not NRW land-use codes; document the source-to-class crosswalk.

## Raster sampling, derived elevations and distances

`raster_evidence` can read numeric or categorical covariates **exactly aligned** with the flood master raster. For example:

```json
[
  {"path":"../data/design_groundwater.tif","field":"design_groundwater_elevation_m","units":"m","band":1,"metadata":{"provider":"...","vertical_datum":"..."}},
  {"path":"../data/surface_elevation.tif","field":"surface_elevation_m","units":"m","metadata":{"provider":"..."}},
  {"path":"../data/protection_classes.tif","field":"protection_zone","units":"category","mapping":{"0":"OUTSIDE","1":"I","2":"II","3":"III"},"metadata":{"provider":"..."}}
]
```

Mismatched rasters fail rather than silently resampling; record a justified alignment operation before use. Register groundwater state and vertical datum separately in evidence. Raster values do not automatically confirm source suitability or official approval.

`derived_module_bases` may explicitly subtract a proposed depth from a surface elevation: `{"design":"rain_garden_infiltration","surface_field":"surface_elevation_m","base_depth_m":0.4,"evidence_ref":"DESIGN_ASSUMPTION_001"}`. This writes a design-specific base elevation. It does not supply design-geometry confirmation or close any other evidence gap.

`distance_evidence` computes geometric minimum distances from each analysis polygon to surveyed reference geometries. Use e.g. `{"path":"../data/assets.gpkg","layer":"non_waterproof_basements","field":"basement_distance_m","coverage_complete":true,"evidence_ref":"SURVEY_001","metadata":{"provider":"..."}}`. Incomplete inventories leave the usable distance unknown. Distances from coarse grid cells are conservative screening distances; replace/split them with actual module footprints before design clearance. A basement or asset **edge** must not be replaced by its centreline. Neighbour setbacks require the relevant neighbouring-property features, not all boundaries including unrelated internal parcel lines.

## Ownership

Supply polygons with a categorical field mapped explicitly to `municipal`, `private`, `other_public` or `unknown`. Overlaps are reported as `conflict`; mixed cells retain every area fraction, and uncovered fractions stay unknown. Conflicting fractions may sum above one and must not be added as disjoint owned area. A generic public-space or land-use map is not legal ownership evidence. Authorized cadastral ownership data may require restricted access. Do not infer owners from OSM.

## Combinations

Declare exact `modules` with `unit_id`, `design`, `module_id`, `footprint_id`, `allocated_area_m2`, `source_id`, `source_fraction`; also supply directed `links`. Members must already have individual evaluations. Space allocations cannot exceed a unit's available area; coincident footprint IDs and duplicate unit-design entries fail. Distinct IDs still require layout verification. In this version, subdivide a unit if you need two separate modules of the same design.

Source fractions represent **newly allocated contributing area**, not performance and not repeated credit at every serial treatment stage. A roof-source module can receive fraction 1; a connected downstream module receives fraction 0 of the same source's *new allocation*, while its inflow is represented by an explicit link. Document the water accounting and verify it in Stage 2. Spatial adjacency does not prove a hydraulic route.

`shared_storage` can register `id`, `capacity_m3`, `allocations_m3`; summed nonnegative allocations may not exceed physical capacity. Boolean review fields remain necessary for actual shared-capacity/temporal behaviour. A connected declared graph does not prove elevations, outlet capacity, transient water balance or downstream safety; the named verification gates require separate evidence. See `config/overlay_examples.json` for a template that deliberately leaves proof unresolved.

## MURIEL

The real-data template enables MURIEL. See [MURIEL.md](MURIEL.md) and [the configuration fragment](../config/muriel_inputs.example.json). Register building/sensitive-object **footprints**, verified municipal land or a categorical ownership layer, polygon road footprints, locally assessed usable multifunctional spaces, and optional directed route lines with evidence. Inventories must cover the study area and its destination search extension, not stop at an administrative border. Missing inputs are conditional; a complete empty inventory is a different observation from an absent inventory. The user-defined ≥10 cm intervention screen remains independent of MURIEL's depth/area criteria.
