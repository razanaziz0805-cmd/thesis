# Planning with a small input set · v0.6

Start with **two spatial datasets**: the study boundary and a numeric, scenario-labelled flood-depth map. Detailed engineering evidence is collected when an opportunity becomes a physical module. This implements the thesis's distinction between spatial opportunity, modelled performance and design/permission feasibility (§5.1; §§5.5–5.6).

| When to add it | Input | What it adds |
|---|---|---|
| Required now | Study boundary with confirmed CRS | Defines the reporting geography; geometry and extent checks |
| Required now | Flood-depth GeoTIFF, or nonoverlapping polygons with depth and unique ID | Need map, connected flood action areas, depth/area register |
| First useful addition | One classified surface polygon layer | Five NbS investigation maps: roof retention, rain gardens, tree/street retrofits, multifunctional spaces, permeable surfaces |
| Optional planning context | Current ownership polygons | City/private/other-public/unknown shares and delivery actions |
| Optional planning context | Published heat-context polygons with explicit priority classes | Heat-priority overlap within each flood action area; unknown coverage retained |
| Add known restrictions early | One polygon layer of documented infiltration-excluded classes; detailed evidence may also be registered | Any intersecting known exclusion retains infiltration FAIL; uncovered areas remain conditional, never automatically allowed |
| For full MURIEL | Building/sensitive-object footprints, verified municipal land, roads, assessed usable spaces | Existing retention protection and connected-retention/routing investigations |
| When designing a shortlisted module | Terrain, base depth, design groundwater/datum, runoff quality, utilities, structural, outlet and operator evidence | Advanced pathway/design qualification before Stage 2 |

A DEM, sewer model, cost database, structural certificates and dozens of engineering Boolean fields are **not required for the first planning run**. They remain necessary where the later decision depends on them. Surface land use does not prove legal ownership; ground-truth checks still matter.

## Three short steps in QGIS

1. Keep **Planning opportunities** selected. Choose the flood map, units, threshold, boundary and workspace. Source grid and depths are preserved by default; automatic preparation checks and aligns registered inputs without guessing unknown CRSs.
2. Open any useful **Optional planning context** section. Select the polygon layer, category field and exact source values for each category. For example, map your recorded roof category to `roof`; do not infer a class from a filename. Unmapped, mixed or uncovered surface classes remain unknown. Record source details. Use **Known infiltration exclusions** for a documented prohibition layer; this is an evidence declaration, not permission to label an unverified constraint as legally confirmed. Detailed groundwater/protection/soil inputs remain supported in registered configurations.
3. Check inputs and create results. Open the offline report for the action register, then `stage1.qgz` for map themes and clickable feature explanations. Disable printing for a quick first run.

The advanced selector retains the original qualification form, MURIEL and registered physical combinations. Existing configurations without `mode` continue to use engineering qualification. Open a registered configuration to preserve multiple evidence layers and advanced mappings; copy it for a new threshold rather than overwrite results.

CLI template: [planning.example.json](../config/planning.example.json). `stage1 init new.json` now creates a planning configuration. For a demonstration:

```bash
/usr/bin/python3 -m stage1 demo --planning --directory outputs/planning-demo
```

## What a Stadt Köln planning meeting can use

- **Flood action areas:** edge-connected mapped areas at or above the configurable depth threshold, without a minimum-area exclusion. A001 etc. give a readable label; geometry-based IDs and source-unit links support the audit. They are discussion areas, not designed detention basins or hydraulic catchments.
- **Delivery register:** mapped area, maximum depth, ownership shares, heat overlap, extent uncertainty and a next action. Municipal land suggests a public-space review; private land suggests owner engagement, agreements and advice. Neither is a technical approval.
- **NbS investigation maps:** five functional families instead of asking a new user to specify all 15 design variants. Surface matches remain CONDITIONAL. Unknown surfaces do not receive a selected typology. Mismatches are NOT_APPLICABLE; a documented land-use conversion requires separate review.
- **Groundwater pathway map:** known failures retain infiltration FAIL. A separate lined/controlled-release concept may be investigated; it is not an automatically approved substitute. Even extensive preliminary evidence does not produce final groundwater PASS before module design.
- **Flood/heat context map:** flood action outlines over published heat classes, with exact intersection shares in the register. No cooling coefficient, degrees of cooling or future heat benefit is invented.
- **MURIEL**, when registered: the existing screen and its reasons/references are retained, including protection of existing retention. Generic flood action areas are not labelled MURIEL-qualified.

The table is ordered by maximum mapped depth, then area, solely to aid browsing. There is no opaque weighted score, risk ranking or implied preference for public over private land. Heat, delivery and data completeness remain separate columns. Receptor importance and safe hydraulic connection require their own evidence.

## Outputs and audit

| File / layer | Purpose |
|---|---|
| `stage1.qgz`, `stage1.gpkg` | Portable QGIS themes and spatial results; identify any feature for reasons |
| `planning_shortlist.csv` / `planning_action_areas` | Flood discussion areas and delivery/investigation next steps |
| `planning_options.csv` / `planning_opportunities` | Five families per source unit, applicability, provisional pathway, infiltration status and references |
| `action_membership.csv` | One-to-many links from source units to action areas |
| `groundwater_screen`, `decision_audit.csv` | Preliminary groundwater gate details; MURIEL decisions when enabled |
| `source_registry.csv`, GeoPackage `input_provenance` | Full rule citations/URLs, verification status and checksummed input metadata |
| `planning_summary.json`, `run_manifest.json` | Areas, unknown coverage, method, versions and limitations |
| `report.html`, PNG/PDF sheets | Offline planning brief and print maps |

NoData and areas outside the supplied flood coverage remain unknown, including in the need map. Action areas touching unknown coverage or the study edge are flagged as potentially incomplete. Corner-touching areas stay separate; shared-edge cells join. Geometry changes between thresholds can split/merge areas, so spatial review and source membership are needed when comparing runs; a label such as A001 is not a persistent rank.

Surface boundaries crossing a cell are retained conservatively as unknown unless the whole cell has a consistent mapped class. Finer output cells do not create finer evidence. The action register also lists surface-matched investigation families. These are alternatives, not tested combinations: shared footprint, capacity and flow links remain unverified.

Ownership and heat intersection shares use the actual polygons; contradictory heat categories contribute to unknown coverage. Ownership overlaps are conflicts and their category fractions must not be summed as disjoint area.

The current cap remains **250,000 source units**; this is not a tiled NRW-wide raster engine. Larger studies need an explicit partition strategy. The planner mode reduces per-unit typology detail and audit overhead, but does not claim a full-city performance benchmark.

## Traceability to the thesis

| Thesis basis | Implementation |
|---|---|
| §4.1; §5.1; §5.5.1 | Planning concepts separated from final design PASS and modelled benefit |
| Table 4.2; §§5.5.2–5.5.4 | Functional palette, conditional water pathways and next investigations |
| §§4.4.2 / 5.5.3; Schwerdorf (2022), slides 19–20 | Existing MURIEL module retained as a separate local screen |
| §§5.4.1 / 5.5.4 | Provenance, ownership, delivery and conditions |
| §5.7.4 | Heat context separate from hydraulic performance |
| §§5.6–5.7 | Detailed qualification, simulation and portfolio comparison remain subsequent decisions |

The default project is generic. Register the actual event, units, suitable projected CRS and local policy for any study area; see [TRANSFERABILITY.md](TRANSFERABILITY.md). No city's technical values are universal. The attached thesis supplies research evidence, not executable instructions. Stage 2 Scenarify and Stage 3 optimisation remain outside this release.
