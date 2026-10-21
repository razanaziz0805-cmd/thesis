# Stage 1: start in QGIS

Use QGIS **3.40 or newer**. The release is tested on QGIS 3.40.6. It runs locally using QGIS's Python environment; there is no server, account or extra Python installation to configure.

## Install the panel

1. Download `nbs-stage1-plugin-v0.6.zip` from this repository's `downloads` folder. On GitHub, open the file and select **Download raw file**. Keep this ZIP intact.
2. In QGIS, choose **Plugins → Manage and Install Plugins → Install from ZIP**, select the ZIP, and install it.
3. Enable **NbS Stage 1 Opportunity Mapping** if necessary. Open **Plugins → NbS planning → NbS Stage 1 · opportunity mapping**.

The package includes its engine. You do not have to select a repository folder. The existing Processing script remains available for graphical models and batch work.

## Prepare your inputs

Click **Prepare GIS data…** for CRS correction/confirmation, clipping, grid choices and a separate input-review project. See [the preparation guide](PREPARATION.md). New guided screening runs also prepare registered inputs on the native flood grid by default.

## First real run

1. Keep **Planning opportunities · start with two layers** selected. In Inputs, enter the study name and scenario. Enter the actual provider event and units, then choose a suitable projected CRS in metres. No event, return period, CRS or city rules are assumed; the 10 cm project screen is configurable.
2. Select the numeric flood map and study boundary, using saved GeoTIFF/GeoPackage files. Choose a raster band or vector depth/ID fields, a workspace and source details. Automatic preparation preserves the native flood grid by default.
3. In **Optional planning context**, open only the sections you have: surface types, ownership or heat. Select each category field and map its exact source values. Leave unknown classes unmapped. No engineering checklist is required.
4. Click **Check inputs**. Correct errors and review warnings. Missing optional data do not block flood action maps; they remain visible as unknown/conditional.
5. Create planning results. Turn off printing for a quick analysis or leave it on for map sheets. Use **Open report** for action areas, ownership shares, heat context and next steps.
6. Open `stage1.qgz`, choose a map theme and use **Identify Features** for reasons/references. Every retained planning concept is CONDITIONAL, not design-approved.
7. Switch to **Advanced** when preparing detailed modules or full MURIEL inputs. The original design evidence, variants and registered physical combinations remain available.

See [the planning guide](PLANNING.md) for the short input table, output register and exact interpretation.

Configurations are saved in `workspace/configurations`; outputs are saved in distinct `workspace/runs` folders. Existing outputs are never overwritten. **Cancel run** takes effect at checkpoints; a single geometry operation or map export may finish first. Cancelled or failed runs do not publish a final result folder.

## More detailed evidence and combinations

The panel accepts a prepared polygon evidence layer using field names in [INPUTS.md](INPUTS.md). Raw soil maps, groundwater elevations or ownership do not by themselves establish all design approvals. Expert evidence remains necessary.

Use **Open registered configuration…** for advanced workflows with multiple evidence layers, field mappings, aligned rasters, surveyed routes, local rule profiles or declared NbS combinations. This preserves those settings. If its output already exists, use **Copy registered configuration for a new threshold run…**: choose the new threshold and workspace. The original configuration and expert inputs are preserved, and the copied configuration can be run directly. The guided form defaults to generic unconfigured rules; load a cited local profile for the governing jurisdiction. See [TRANSFERABILITY.md](TRANSFERABILITY.md).

## Read the report

Both reports work offline. The default planning brief provides a searchable action-area table, ownership filters, next steps and map sheets. The advanced report includes flood-need and unknown-data counts, links to QGIS/PDF/CSV outputs, searchable map sheets, map-group filtering, and an expandable list of evidence tasks. `evidence_tasks.csv` includes actions, responsible parties and source references. Counts refer to analysis units or rule evaluations, not independent projects or measured flood benefits.

## Command line

Use the QGIS Python interpreter. In this cloud environment:

```bash
/usr/bin/python3 -m stage1 validate config/your_run.json
/usr/bin/python3 -m stage1 run config/your_run.json --no-maps
/usr/bin/python3 -m stage1 run config/your_print_run.json
/usr/bin/python3 -m stage1 demo --planning --directory outputs/new-demo
```

`validate --json` returns machine-readable issues and exits with status 2 on errors. Runs show phase/unit progress. `--quiet` hides progress, and `--debug` before the command enables a technical traceback. `/usr/bin/python3 -m stage1 gui` opens the same panel when a graphical display is available. Use the plugin inside desktop QGIS on Windows/macOS.

## What the engine does not establish

Admissible means the represented screening gates have evidence. It does not mean construction permission or a demonstrated hydraulic benefit. Missing data remain conditional/unknown; hard failures are not converted to passes. Demonstration maps use synthetic data. Stage 2 hydraulic simulation and Stage 3 Pareto assessment remain separate work.
