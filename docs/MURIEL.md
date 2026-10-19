# MURIEL public-space screening · v0.2

This is an executable addition to Stage 1. It was previously documented but not implemented. The module now runs after the preliminary groundwater screen and retains that screen's pathway restrictions independently.

Read thesis **§4.4.2**, **§5.5.3**, Table 4.2 and the relevant groundwater/pathway paragraphs first. The original [Schwerdorf (2022) presentation](https://www.region-koeln-bonn.de/fileadmin/redaktion/pdf/regionaler_fachdialog/rkb-regionaler-fachdialog-starkregen-schwerdorf.pdf) was then retrieved and its **slides 19–20** checked. These specify the query tree, the 70% existing-retention interpretation, the nearby-space/topographic-adaptation branch and the no-destination/object-protection branch.

Retrieved presentation SHA-256: `7c710865f2516891fb5340fc8e3a0077de308614db5e6c8325a8477808ef73ec`. The PDF is referenced, not redistributed in the package.

## Registered criteria

| Test | Default | Interpretation |
|---|---:|---|
| Flood footprint | `depth_mask` | Dissolve adjacent cells/polygons with depth **>0.30 m**; point-only contacts remain separate |
| Hotspot area | **>2,000 m²** | Compute dissolved polygon area, not individual cell area |
| Depth | **>0.30 m** | Strict; exactly 30 cm is excluded from the default mask |
| Building / sensitive object | **<1 m** | Exact edge-to-edge distance; source described a 1×1 m raster, so source accuracy matters |
| Municipal non-road land | **<50 m** | Verified city-owned geometry after road footprints and conflicting non-city claims are removed |
| Usable municipal destination | **≤100 m** | “Within 100 m” implemented inclusively; record any changed convention |
| Existing retention overlap | **≥70%** | Union of eligible usable-space intersections divided by registered flood-footprint area |

These are **local Porz/Eil planning-screen parameters**, not NRW-wide design or permit requirements. They are configurable under `muriel.thresholds`, and are recorded in every run.

The original presentation labels its flood areas “>30 cm, >2,000 m²”. Thesis §5.5.3 instead describes a **maximum-depth** condition. Both interpretations are supported:

- **`depth_mask` (default):** select cells/source polygons deeper than the depth criterion, dissolve connected pieces, then test area. This follows the original presentation's depth-labelled flood-area definition.
- **`inundation_maximum`:** dissolve depth above `flood_extent_depth_m` (default 0 m), then test area and maximum source depth. This follows the thesis's maximum-depth wording.

Choose and state one in the methodology before comparing results. They can produce different footprint areas, candidates, hotspot IDs and retention-overlap fractions. Neither definition changes the independent ≥10 cm flood-need map. The source-mask map and rule audit explicitly expose the chosen mode. A coarse polygon depth attribute can only support its stated source statistic; the engine does not invent subpolygon depth boundaries.

## Planning decisions and statuses

| `planning_class` | Meaning / next action |
|---|---|
| `PROTECT_RETENTION` | At least 70% already overlaps verified usable municipal non-road space. Protect the existing function; do not automatically propose construction. |
| `RETROFIT_CANDIDATE` | Local spatial filters passed and a specific directed route has referenced topographic, safe-flow, receptor and land-control evidence. Investigate/design and model; this is not approval. |
| `ROUTING_INVESTIGATION` | Eligible space is nearby, but route evidence is incomplete. Examine whether topography/flow can be adapted safely. |
| `NO_DESTINATION` | Complete verified inventories show no eligible destination within the radius. Consider blue-green streets, object protection or another pathway. |
| `OUTSIDE_PRIORITY` | A known building-adjacency or municipal-land distance criterion fails. This does not imply no flood need or no other NbS opportunity. |
| `ROUTE_UNSUITABLE` | Every assessed applicable route fails a topographic, safe-flow, endpoint or receptor test. Redesign or use another pathway. |
| `BELOW_SCREEN` | Known observed footprint does not meet the strict area/depth screen. Retained in the audit. |
| `EVIDENCE_GAP` | Missing coverage, references, land/usability evidence, boundary truncation or adjacent NoData prevents a definitive interpretation. |

`status` separately records the applicable gate result (ADMISSIBLE / CONDITIONAL / FAIL). A protected retention function remains visible even when it fails another *priority* filter, such as building adjacency. Thus `planning_class=PROTECT_RETENTION` and `status=FAIL` can coexist: protect the known function, but do not claim that every local priority criterion passed. These fields are not construction authorization.

Missing data never imply no buildings, no roads or no destinations. Known positive observations can establish proximity even with an incomplete inventory; absence requires complete coverage. Flood polygons touching the AOI, adjacent NoData or uncovered vector coverage remain extent-conditional. A zero observed hotspot count with unknown source cells is not proof of no hazard.

## Inputs and execution

Use the [configuration fragment](../config/muriel_inputs.example.json). Paths resolve relative to the complete run JSON. Every input needs dated provenance, a source/evidence reference and an explicit coverage statement.

- **`receptors`**: one or more polygon footprint inventories, including buildings and relevant sensitive objects. Use true footprints; a centroid is not a building edge.
- **`municipal_land`**: verified prefiltered city land, or an ownership layer with `class_field` and `municipal_values`. When a categorical layer has overlapping private/unknown claims, those claims are removed conservatively from the municipal selection; conflict prevents a complete-coverage claim.
- **`roads`**: actual road-footprint polygons. Do not guess a buffer around centrelines. A complete, genuinely empty inventory is supported; an absent inventory is unknown.
- **`usable_space`**: polygons with unique `destination_id` and a true/false/null `usable` field. Alternatively use `usable_field` with an explicit `usable_mapping` from source categories to booleans. Unmapped categories remain unknown. The classification must document locally appropriate multifunctional use. A green colour on a land-use map is not evidence of safe temporary flooding.
- **`routes` (optional)**: directed line geometries and referenced assessment fields. Without these, nearby spaces remain routing investigations.

Land/road/space inventories must cover the AOI **and the destination search extension**. The geometry operations keep relevant data outside the administrative boundary. Actual modelling may need a larger hydrological domain.

```bash
cd /workspace/thesis
QT_QPA_PLATFORM=offscreen XDG_CACHE_HOME=/tmp/thesis-qgis-cache \
  /usr/bin/python3 -m stage1 demo --muriel --directory outputs/my-muriel-demo
# After registering actual inputs in a copied configuration:
/usr/bin/python3 -m stage1 run config/your_run.json
```

The real-data template enables MURIEL with missing inventories left explicit. The general legacy demonstration remains available without `--muriel`. The same run JSON also works through the existing QGIS Processing entry.

## Route evidence

Each line must identify the exact `hotspot_id` and `destination_id`. The line's first vertex must lie in/on that hotspot and its last vertex in/on the selected destination. A single directed, nonzero-length route is required. Record `topography_compatible`, `flow_routing_safe`, `downstream_receptors_safe`, `route_land_control_ok`, and `evidence_ref`. Missing proof is conditional; assessed incompatibility fails the route. Land-control gaps remain conditional.

These fields represent a **referenced survey/design assessment**, not a conclusion automatically inferred from distance. No DEM, inlet/outlet model, earthworks design or hydraulic simulation has been supplied for Köln-Kalk. A proximity-only line is the shortest geometric connector and is dashed explicitly. It is not a predicted flow path. For overlapping polygons, a zero-length proximity line is retained as a non-geometric connection record rather than inventing a route.

Unknown hotspot/source-space IDs are validation errors. If a previously declared destination becomes unverified/ineligible, or a pair lies beyond the registered radius, its line is retained with a conditional/fail reason and cannot make the destination eligible. A changed footprint definition may change hotspot IDs; refresh the hotspot register and route crosswalk deliberately.

## QGIS deliverables

The GeoPackage contains:

| Layer / register | Contents |
|---|---|
| `muriel_source_mask` | Every input unit's inclusion/exclusion/unknown decision and rule source |
| `muriel_hotspots` | Dissolved footprints, area, maximum depth, source-unit IDs, threshold and extent decisions |
| `muriel_priority` | Planning class, gate status, distances, overlap %, groundwater crosswalk, complete explanation |
| `muriel_destinations` | Usable space clipped to verified municipal non-road land; source/eligible areas and evidence |
| `muriel_connections` | Supplied routes and clearly distinguished proximity connectors with pair-level reasons |
| `muriel_context` | Building/receptor, road, public-land and flood-footprint context |
| `decision_audit` | One row per source-mask, screening or route rule, including observed/expected values, citation, evidence, responsibility and closure |

Empty hotspot/destination/connection sets are reported in `muriel_summary.json`; the source-mask map still explains the observations. The QGIS project has five dedicated map themes/layouts when all five result sets exist. `muriel_atlas.pdf` collects those sheets, while `stage1_atlas.pdf` includes the complete workflow. CSV registers and checksummed provenance remain alongside the maps.

Use **Identify Features** and expand `explanation`. For numerical comparison, inspect `area_m2`, `max_depth_m`, `receptor_distance_m`, `municipal_distance_m`, `destination_distance_m`, `overlap_percent`, `reason_codes` and the linked identifiers. All map sheets show the local criteria, scenario, CRS, source-grid description, footprint mode, references and run ID.

## Demonstration and limits

The dedicated artificial district includes seven observed >30 cm footprints: one existing retention function, one route-evidenced retrofit, one routing investigation, one no-destination alternative, one outside the adjacency filter, one exactly 2,000 m², and one incompatible route. An exactly 30 cm polygon and a 10 cm shallow apron appear in the source-mask exclusions, plus a NoData source unit. Four 20×40 m pieces dissolve into a 3,200 m² hotspot with 75% eligible overlap. In maximum-depth mode its connected shallow apron changes the area to 4,000 m² and the overlap denominator, deliberately illustrating the interpretation sensitivity.

**All demonstration geometry and route evidence are synthetic.** Actual Köln-Kalk maps require the registered real GIS inputs. MURIEL does not establish infiltration clearance, absence of contamination, flood-reduction benefit, structural safety, drainage capacity or permission. The independent Stage 1 NbS gates and later Scenarify checks remain necessary for a proposed design.
