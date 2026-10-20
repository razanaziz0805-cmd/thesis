# Automatic GIS preparation (v0.4)

The preparation stage creates new files. It never edits uploaded sources, guesses an unknown CRS, converts land use into ownership, or interprets soil/profile heights as groundwater.

## Desktop QGIS

Open the Stage 1 panel and select **Prepare GIS data…**. Choose a study boundary, target CRS (normally EPSG:25832), workspace and input files. For raster inputs select a master raster. A cell size of zero preserves its native grid; choose a positive size only for a documented target grid. Set raster kinds to continuous, categorical or flood depth, and choose a compatible resampling method. Optional source CRS overrides require an evidence reference. A bare boundary may be accepted as geometry only after its CRS is confirmed. Other shapefiles normally need their attributes.

For a multi-layer GeoPackage, enter the exact layer name in the input table. Add each required layer separately. The table scrolls horizontally to show per-dataset CRS, references and repair options.

Preparation produces:

- `prepared.gpkg`: dissolved boundary and transformed/clipped vector layers, retaining fields and original feature IDs in `prep_source_fid`;
- `rasters/*.tif`: north-up rasters on one exact grid, with unknown/outside cells represented as NoData;
- `prepared_inputs.qgz`: portable QGIS project for reviewing coverage/alignment;
- `preparation_manifest.json`: input checksums, code/software versions, CRS assignments/transformations, grid, original resolution, clipping scope, data counts and limitations;
- `preparation_job.json`: the choices needed to repeat the preparation;
- `geometry_repairs.csv`: feature-level changes if repair was explicitly enabled. Repairs require review.

In the normal **Inputs** form, **Automatically reproject, clip and align inputs to the native flood grid** is enabled for new guided setups. It prepares the registered inputs before screening and saves a `prepared_run.json`. Registered configurations retain their existing settings; enable `preparation` explicitly for them. Completed preparation is preserved separately if a later screening check fails, so it can be reviewed/reused.

## CRS handling

A known CRS is transformed to the target CRS. A missing CRS needs `source_crs` plus `crs_evidence_ref`. A demonstrably wrong declared CRS can be replaced using the same documented override; this assigns the correct interpretation before reprojection. The manifest distinguishes assignment, replacement and transformation. Geographic coordinate ranges and spatial coverage are checked. Ballpark coordinate transformations are disabled.

CRS labels, coordinate ranges and overlap do not establish survey accuracy. Small offsets, historical transformations and wrong-but-plausible coordinates need authoritative reference/control data. Z values and vertical datums are not certified or automatically converted.

## Grid and NoData

Use the **flood provider's original grid** as the analysis master. Preserve its origin and cell sizes by default. Native clipping retains source cell IDs, including the source row/column offset, so ID-joined evidence continues to match. Reprojection, resolution changes and shifted grid origins invalidate those ID joins; use spatial evidence or explicitly remap it. Declared combination modules also require remapping when the grid changes.

Flood resolution/origin changes need a `resampling_evidence_ref`. Nearest-neighbour retains sampled values; explicitly chosen maximum aggregation can support conservative coarse screening, but alters depth/area interpretation and does not conserve flood volume. It is not a replacement hydraulic simulation. MURIEL and the 10 cm boundary can both change after regridding.

Categorical inputs permit nearest-neighbour or mode. Continuous inputs permit nearest-neighbour, bilinear or average. Defaults use nearest-neighbour; no method creates finer source information. Upsampling a 50 m soil layer to a 1 m flood grid still represents 50 m source information. This version does not interpolate sparse soil points into area-wide suitability.

Raster scale/offset encodings need a documented physical-unit conversion before screening. Conflicting declared/configured flood units are rejected during preparation. Int64/UInt64 rasters require a separately verified lossless strategy. Other common raster types are exported to Float64, preserving Float32 and <=32-bit integer values and allowing NaN NoData. Outside/unknown values never become zero or a passing category. Boundary-intersecting source cells are retained using an all-touched mask, then clipped as analysis polygons.

Vector inventories normally retain a **100 m search extension**, increased automatically if MURIEL's destination radius is larger. Inventory completeness flags are preserved, not invented. Distance inventories remain uncut in integrated preparation so a nearest asset beyond the buffer is not silently lost. Native raster preparation retains the provider's actual coverage; it does not invent source coverage outside it.

## Incomplete inputs

A missing `.shx` can be rebuilt on an isolated copy. Missing `.dbf` attributes cannot be reconstructed from geometry. A lone `.dbf` cannot supply location; `.shp.xml` is metadata rather than the actual layer. Re-exporting a complete GeoPackage is usually the simplest remedy. Duplicate files are flagged in the read-only inventory and not treated as independent evidence.

Point/line data retain their geometry types. No arbitrary buffers manufacture buildings, municipal land or utility protection corridors. Unknown physical units and absent technical/authority evidence remain unresolved after preparation.

## Command line and configuration

```bash
/usr/bin/python3 -m stage1 inventory data/*.gpkg data/*.tif data/*.shp --output outputs/inventory
/usr/bin/python3 -m stage1 prepare config/preparation_job.json
/usr/bin/python3 -m stage1 run config/your_run.json
```

`inventory` exits with code 2 when inputs are incomplete or unreadable; the report explains each issue. It does not modify sources. For a standalone job see [preparation.example.json](../config/preparation.example.json). Job paths are relative to the job file; source overrides are per dataset.

Enable integrated preparation with:

```json
"preparation": {
  "enabled": true,
  "search_buffer_m": 100,
  "grid": {}
}
```

The native flood master is selected automatically. Prepared files normally go to `<output_dir>_prepared`; that folder and screening results cannot overwrite existing runs. Cancellation/failure cleans unfinished staging files. Single GDAL/GEOS operations may finish before cancellation is observed. Prepared inputs alone are not an opportunity-map or final engineering result.
