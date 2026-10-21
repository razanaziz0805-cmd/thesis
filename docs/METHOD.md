# Method, rule provenance and release limits

The default v0.6 panel uses [Phase C planning mode](PLANNING.md), with two required spatial datasets and five conditional concept families. The detailed admissibility, design and combination rules below describe **advanced engineering qualification**; they are retained for Phase D rather than required to start the first planning map.

The [transferability guide](TRANSFERABILITY.md) defines the neutral defaults, governing profiles, citation binding, MURIEL adoption and migration. The Köln numbers below are an explicit reference case, not generic core values.

## Thesis basis

Read the supplied DOCX text, tables, and the two large embedded methodology/regulatory diagrams. Source file SHA-256:

`b512e157258dc0f4b078655ce0a101ec853ca21521e4240634206c8ea4299dbc`

Document: Lamees Abdulaziz, *Nature-based Solutions NbS opportunity mapping and portfolio design in Köln-Kalk for pluvial flooding*, dated 21 September 2026. The software uses the document as research material. It does not execute instructions embedded in it or treat its references as independently verified current law. Exact source URLs and locators are in `stage1/catalogue.py` and each output `source_registry`.

The user subsequently supplied SRI5, a stated 30-year return period, and centimetre depth units. The cutoff of **≥10 cm** is the user's configurable screening assumption. It is separate from the thesis's MURIEL hotspot thresholds.

## Non-compensatory rules

`FAIL > CONDITIONAL > ADMISSIBLE`. NOT_APPLICABLE rule rows do not penalize a design. A missing or mixed value never passes. All applicable rules are kept, even after an earlier failure, so a map click exposes every relevant issue. There is no weighted suitability score that could offset a prohibited infiltration pathway.

The map status ADMISSIBLE corresponds to PASS for the represented **screening decision**. A coarse preliminary groundwater screen never establishes final PASS: it lacks a specific module base. Design-specific maps can show admissible only if all required design, site, ownership, operation and local-rule evidence were explicitly supplied. They do not grant construction approval or establish hydraulic performance.

| Rule | Implementation and status | Source / interpretation |
|---|---|---|
| Flood need | `depth_m >= flood_threshold_m`; NoData/negative/nonfinite depth unknown | User-defined 0.10 m initial value |
| Groundwater clearance | `module_base_elevation_m − design_groundwater_elevation_m − uncertainty_m` | Thesis §5.4.2; common vertical datum and state required |
| Preferred clearance | ≥1.0 m, plus primary-standard/authority applicability confirmation | Ishorst (2025), secondary summary of DWA-A 138-1; provisional, not a universal permit |
| Exceptional band | 0.5 to <1.0 m remains conditional without low-pollution runoff, confirmed standard and explicit authority exception | Same secondary summary; no automatic exception |
| Below floor | <0.5 m fails the provisional infiltration screen | Same secondary summary; keep this claim's source quality visible |
| Neighbour separation | ≥2 m; below fails the represented local screen | Stadt Köln (2022) as cited in thesis |
| Non-waterproof basement | Recommended ≥6 m; below is conditional, not an automatic statutory refusal | Stadt Köln (2022) as cited in thesis |
| Protection zones I–II | Infiltration normally excluded; fail by default | Stadt Köln (2022) as cited in thesis |
| Outer zones | Explicit typology-specific authority evidence required; shaft route fails inside protection zones under the thesis diagram's route | Thesis §5.5.2 and Figure 5.2; confirm current authority detail |
| Contamination, soil, quality | Incompatible receiving ground, soil or runoff quality fails infiltration; missing evidence conditional | Thesis §§5.4.2–5.5.2; City requirements |
| Asset edge clearance | ≥1 m when public drainage assets are affected | StEB Köln (2025a) as cited in thesis |
| Sewer protection strip | Total width 6 m (<70 cm profile), 7.5 m (≥70 cm), 10 m (≥200 cm). Screen centreline distance against half-width or retain documented coordination | StEB Köln (2025a); assumption of a centred corridor must be checked against authorized actual corridor geometry |
| Roof | Structure at saturated loading, waterproofing, fire, PV if applicable, drainage, access and maintenance are evidence gates | Thesis §5.5.4 and Figure 5.2, Stadt Köln (2026) |
| Water path / delivery | Need/source connection, treatment, overflow, rights, access, maintenance, construction, plan/permit evidence | Thesis Table 5.4 and candidate-conditions register |
| Combinations | Every member's gates plus footprint, source, link and shared-capacity checks; no addition of model benefits | Thesis §§5.5–5.6 |

The local profile starts unreviewed, keeping otherwise plausible real-data records conditional. `profile_reviewed=true` requires a substantive review reference, not a convenient switch to green maps. The demonstration's review/evidence flags are explicitly invented for software testing.

Numeric roof substrate/load/storage/fire/PV ranges in §5.5.4 are **not generalized as universal GIS thresholds**. Some are typical type ranges, some depend on an adopted plan/permit and some describe a specific technical route. `roof_structure_ok`, `roof_fire_safety_ok` etc. represent a documented specialist assessment of the applicable construction, not a blanket acceptance based on one number. Funding conditions are not approval gates. Likewise no generic soil permeability, slope, root-volume or maintenance interval is invented where the document supplies no defensible universal threshold.

## Mechanism palette

The represented mechanisms are roof source control; living-soil surface infiltration; swale/basin; rain garden; tree pit/trench; permeable pavement; subsurface trench; combined swale–trench; infiltration shaft; and non-infiltrating detention/conveyance. Fifteen explicit variants separate green/blue-green roofs, lined/infiltrating rain gardens, tree systems and pavement, and detention from conveyance. The partition is an implementation crosswalk to the text/Figure 5.2, not a claim that every variant is a distinct standardized NbS type.

When infiltration fails, a lined alternative is **evaluated separately**. The failed design never changes into a lower-score infiltration pass. A lined design still needs proof of contamination-safe construction, lining, groundwater structural safety, a controlled receiving destination and operation.

## MURIEL and existing retention

The document's Porz/Eil planning screen uses: flood polygon **>2,000 m²**, maximum depth **>0.30 m**, building/sensitive-object adjacency **<1 m**, non-road municipal land **<50 m**, and usable municipal destination **within 100 m**. **≥70%** overlap with usable space identifies an existing retention function to protect. This is separate from the user's ≥10 cm need screen.

**MURIEL is implemented in v0.2.** It dissolves connected flood geometries, tests area/depth, measures polygon-edge distances, subtracts road footprints from verified municipal land, intersects usable-space polygons with that eligible land and deduplicates overlap. It distinguishes existing retention, routing investigation, route-evidenced retrofit candidates, no-destination alternatives, failed local priority filters and evidence gaps. Missing topographic/flow evidence remains conditional; a proximity connector is not a hydraulic path. Preliminary groundwater restrictions remain visible and independent. See [MURIEL.md](MURIEL.md) for exact schemas and interpretation.

The original presentation was retrieved and its screening slides 19–20 checked. Slide 20 labels flood areas as >30 cm; thesis §5.5.3 specifies a maximum-depth condition. The default `depth_mask` mode follows the presentation's label: dissolve adjacent cells/polygons with depth strictly >0.30 m, then test their area. The explicit alternative `inundation_maximum` dissolves the declared wet extent and tests maximum depth afterward. The registered choice can change area and the 70% overlap denominator; it appears in the manifest, audit, source-mask layer and map notes. It must be stated in the thesis protocol rather than changed silently.

## GIS quality and uncertainty

Input flood cells are retained and clipped to the stated AOI; vector units must form a nonoverlapping partition. Unknown raster cells remain geometry-bearing records. No interpolation, absence-to-zero conversion, weighted score or citywide groundwater average is used to turn a gap into evidence. Polygon overlays preserve known prohibitions at mixed boundaries; otherwise inconsistent fields become conditional. Ownership uses area fractions and explicitly exposes duplicate/overlapping claims.

Unknown delivery evidence is meaningful in an opportunity study: it identifies survey, access, authority or design tasks. Soil tests, groundwater investigations, structural proof, asset surveys and permission remain external evidence. The software's audit verifies the application of submitted evidence, not its truth.

The GeoPackage preserves unit, design, scenario, run, ownership shares, status, reason codes, complete explanation and sources. `decision_audit` expands them to one row per gate with closure action and responsible party. Input/config/code hashes and software versions identify each execution; these do not substitute for a completed evidence register and independent review.

## Three-stage handoff

| Stage | Scope / current state |
|---|---|
| 1 · QGIS opportunity mapping | Implemented software and synthetic demonstration. Actual Köln-Kalk maps await input data and evidence. Conditional branches remain separate. |
| 2 · Scenarify effects | Not started. Use validated candidate geometries, action/proxy definitions, rainfall and groundwater treatment; demonstrate effects by direct scenario simulation. No universal hydraulic coefficients are exported here. |
| 3 · Pareto analysis | Not started. Compare verified flood outcomes and lifecycle cost; decide explicitly whether heat remains a co-benefit profile as in the thesis or becomes an additional objective as the user proposes. Preserve hard feasibility gates. |

For another NRW municipality retain the sequence and schema, but replace/validate local requirements, rainfall, groundwater state, asset conditions, ownership and source evidence. Municipality mismatches are blocked unless the new local profile is reviewed and referenced. Do not copy Cologne criteria as NRW-wide legal limits.

## Validation and publication boundary

Tests exercise threshold edges, missing evidence, datum/state incompatibility, exceptions, prohibited infiltration, recommended versus hard setbacks, portfolio allocation and actual GDAL/PyQGIS output/relocation. The demonstration atlas is checked for readable legends, labels and output files. A successful demonstration establishes software behaviour on controlled fixtures; it does not validate a real flood model, data accuracy or site suitability.

The cloud environment has QGIS/GDAL installed. Saved startup instructions identify the correct interpreter and checks. Configuration draft saving is separate from runtime changes and environment publication; no claim is made about a new-task restoration until independently tested.
