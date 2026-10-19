# Validation record

Validated in the attached cloud machine using system PyQGIS **3.40.6-Bratislava**, GDAL **3.10.3**, NumPy **2.2.4**, Qt SVG and Poppler's PDF merger. No extra packages or secret bindings were required.

The v0.2 validation executed **84 tests**, all passing, with none skipped, including the original 48 checks plus MURIEL decision and spatial-integration tests. **Version 0.3 now passes 103 tests**; its additional checks and benchmark are recorded below.

Coverage includes inclusive 10 cm threshold and a changed threshold; centimetre conversion; unknown/negative/nonfinite/NoData depths; groundwater floor/preferred boundaries and explicit exceptions; uncertainty, vertical datum and groundwater-state mismatch; missing design bases; contamination and protection zones; hard versus recommended offsets; lined variants retaining independent gates; local profile transfer; source, space, footprint and shared-storage double counting; missing/invalid hydraulic links; mixed/unknown/conflicting ownership fractions; tiny known prohibitions in conservative overlays; aligned versus misaligned rasters; derived design elevations without automatic approval; complete versus incomplete distance inventories; vector flood inputs and overlap rejection; input hashes, saved CRS and complete audit records; refusal to overwrite previous results; QGIS Processing execution without clearing a GUI project; and reopening the project after relocation.

The audit-table export exposed a QGIS/OGR interaction between no-lock SQLite readers and later write-ahead-log connections. The output now uses normal SQLite locking consistently in saved layer URIs, and the tests assert no GDAL failure during generation. Staged writes and standard GDAL feature-count metadata preserve complete GeoPackage tables. This issue was fixed without discarding errors or weakening decision checks.

The demonstration uses **120 artificial 20 m cells**, 15 design variants (**1,800 unit-design records**) and four declared combinations. It intentionally contains 9/10/11 cm boundary depths, flood NoData, prohibited and missing groundwater evidence, contamination, pending decisions, mixed ownership, overlapping ownership claims and source double counting. Expected combination statuses are one admissible screening result, one conditional branch and two failures. The preliminary groundwater map never reports final admissibility.

The original full demonstration exports **22 map sheets**. The separate `demo --muriel` fixture exports **23 sheets**, including **five dedicated MURIEL sheets** and a separate `muriel_atlas.pdf`. Both workflows create a portable QGIS project with named map themes, an analytical GeoPackage and CSV/provenance registers. MURIEL tests cover strict 2,000 m² / 0.30 m / 1 m / 50 m boundaries; inclusive 100 m / 70% boundaries; connected-component dissolution; diagonal separation; footprint interpretation; excluded 30 cm values; NoData and uncovered extent; roads; private and overlapping ownership claims; missing inventories; source traceability; route endpoints and direction; out-of-radius or ineligible routes; zero observed hotspots; and project relocation.

All synthetic observations, structural/authority decisions and review references are invented software fixtures. The demonstration does not validate Köln-Kalk flood depths, ownership, actual site suitability or legal approval. Earlier source requests were blocked; Schwerdorf's original presentation is now accessible, was downloaded, and slides 19–20 were checked. Its SHA-256 is recorded in MURIEL.md. Other legal/technical sources and the real-data analysis still require verification. No actual Köln-Kalk map, Scenarify run, thermal prediction, lifecycle cost or Pareto front has been validated.

## Version 0.3 usability and optimisation validation

`bash scripts/test.sh` now executes **103 tests**, all passing with none skipped. Added checks exercise read-only input diagnostics, CLI error/exit handling, exact nearest distances for polygons with holes, field-specific overlay coverage, CSV fidelity including multiline/Unicode/missing values, cancellation before and after database creation, cleanup after write failure, progress/timing output, portable projects from staged output, the native QGIS form, threshold-copy preservation, and the actual installable plugin ZIP. The plugin test extracts the ZIP, activates its menu/dialog and executes the bundled engine while preserving an unsaved QGIS project.

The final v0.3 MURIEL demonstration exports 23 map sheets. All 5,594 decision-audit records, 210 candidate records, seven MURIEL decisions, five connections and five destinations match the v0.2 demonstration. GeoPackage integrity, relative layer paths, atlas page counts and manifest code hashes were verified. The report was rendered in Chromium with its local image assets embedded for this cloud's browser test; map-group filtering (23 maps → five MURIEL maps), text search (two tree maps), result-file targets, mobile page width and absence of JavaScript errors were checked. The QGIS panel and dashboard were also visually reviewed.

### Performance evidence

[Raw before/after samples](benchmark-v0.3.json) use the same synthetic benchmark script, system QGIS 3.40.6 and five repetitions per version. The baseline is commit `488a43c`. Source input generation is excluded from timings; full workflow timings include reading, evaluating, writing registers and building the QGIS project, with map printing disabled.

| Benchmark | v0.2 median | v0.3 median | Result |
|---|---:|---:|---|
| 250 evidence overlays; 40 fields over ten pieces | 0.983 s | 0.211 s | About 4.7× faster |
| Full 120-cell, 15-design, four-combination demonstration | 1.464 s | 1.258 s | About 14% less elapsed time |

Run `/usr/bin/python3 scripts/benchmark_engine.py --repeat 5` to measure the current version. Samples vary with hardware, caching and concurrent processes. These small synthetic timings do not establish full-city capacity. The workflow still retains complete feature explanations and audit rows in memory; large/high-resolution NRW studies require documented partitioning rather than silent coarsening. No Windows/macOS desktop installation or real-data hydraulic outcome has been validated here.
