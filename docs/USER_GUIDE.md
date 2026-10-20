# Stage 1: start in QGIS

Use QGIS **3.40 or newer**. The release is tested on QGIS 3.40.6. It runs locally using QGIS's Python environment; there is no server, account or extra Python installation to configure.

## Install the panel

1. Download `nbs-stage1-plugin-v0.4.zip` from this repository's `downloads` folder. On GitHub, open the file and select **Download raw file**. Keep this ZIP intact.
2. In QGIS, choose **Plugins → Manage and Install Plugins → Install from ZIP**, select the ZIP, and install it.
3. Enable **NbS Stage 1 Opportunity Mapping** if necessary. Open **Plugins → NbS planning → NbS Stage 1 · opportunity mapping**.

The package includes its engine. You do not have to select a repository folder. The existing Processing script remains available for graphical models and batch work.

## Prepare your inputs

Click **Prepare GIS data…** for CRS correction/confirmation, clipping, grid choices and a separate input-review project. See [the preparation guide](PREPARATION.md). New guided screening runs also prepare registered inputs on the native flood grid by default.

## First real run

1. In **Inputs**, enter the study name and scenario. Defaults are SRI5, a user-stated 30-year return period, centimetre flood depths and a 10 cm intervention threshold. Confirm the event metadata with the provider.
2. Select the flood-depth raster and study boundary from QGIS, or use **Add file…**. Choose the raster band. For polygon flood data, choose unique ID and numeric depth fields. Use saved GeoTIFF/GeoPackage inputs; export temporary or filtered layers first.
3. Choose a workspace folder and the NbS designs to assess. Open **Source…** for each supplied layer to record its provider, date, version and licence.
4. In **Evidence & MURIEL**, optionally add prepared site/groundwater evidence, ownership, buildings/sensitive objects, road footprints and locally assessed multifunctional spaces. Enter the ownership category mapping and destination fields. Coverage and review checkboxes are explicit evidence declarations, initially unconfirmed. Record a dated local rule review reference if a review is confirmed.
5. Click **Check inputs**. Fix errors; review warnings. Missing evidence allows a screening run but stays conditional in its decisions. Validation checks file/field/CRS/grid readiness; full geometry and rule checks also occur during execution.
6. In **Run & results**, turn off printing for a faster first analysis, or leave it on for PNG sheets and PDF atlases. Click **Run Stage 1**.
7. Use **Open report** or **Open results folder**. Open `stage1.qgz`, select a named map theme, and use **Identify Features** to see the explanation, rule, reference, evidence and follow-up action.

Configurations are saved in `workspace/configurations`; outputs are saved in distinct `workspace/runs` folders. Existing outputs are never overwritten. **Cancel run** takes effect at checkpoints; a single geometry operation or map export may finish first. Cancelled or failed runs do not publish a final result folder.

## More detailed evidence and combinations

The panel accepts a prepared polygon evidence layer using field names in [INPUTS.md](INPUTS.md). Raw soil maps, groundwater elevations or ownership do not by themselves establish all design approvals. Expert evidence remains necessary.

Use **Open registered configuration…** for advanced workflows with multiple evidence layers, field mappings, aligned rasters, surveyed routes, local rule profiles or declared NbS combinations. This preserves those settings. If its output already exists, use **Copy registered configuration for a new threshold run…**: choose the new threshold and workspace. The original configuration and expert inputs are preserved, and the copied configuration can be run directly. The guided form uses the provisional Cologne profile; another municipality needs its own documented local review.

## Read the report

The report works offline. It includes flood-need and unknown-data counts, links to QGIS/PDF/CSV outputs, searchable map sheets, map-group filtering, and an expandable list of evidence tasks. `evidence_tasks.csv` includes actions, responsible parties and source references. Counts refer to analysis units or rule evaluations, not independent projects or measured flood benefits.

## Command line

Use the QGIS Python interpreter. In this cloud environment:

```bash
/usr/bin/python3 -m stage1 validate config/your_run.json
/usr/bin/python3 -m stage1 run config/your_run.json --no-maps
/usr/bin/python3 -m stage1 run config/your_print_run.json
/usr/bin/python3 -m stage1 demo --muriel --directory outputs/new-demo
```

`validate --json` returns machine-readable issues and exits with status 2 on errors. Runs show phase/unit progress. `--quiet` hides progress, and `--debug` before the command enables a technical traceback. `/usr/bin/python3 -m stage1 gui` opens the same panel when a graphical display is available. Use the plugin inside desktop QGIS on Windows/macOS.

## What the engine does not establish

Admissible means the represented screening gates have evidence. It does not mean construction permission or a demonstrated hydraulic benefit. Missing data remain conditional/unknown; hard failures are not converted to passes. Demonstration maps use synthetic data. Stage 2 hydraulic simulation and Stage 3 Pareto assessment remain separate work.
