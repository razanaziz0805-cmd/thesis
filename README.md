# Auditable NbS opportunity mapping · Stage 1

This repository implements the **first stage** of the thesis workflow: configurable flood-need maps, a preliminary infiltration-pathway map, **MURIEL public-space screening**, per-design opportunity maps, declared combination checks and ownership analysis. It produces a portable QGIS project, a GeoPackage with feature-level explanations, audit tables, CSV registers, PNG sheets and PDF atlases.

**Current status (v0.4):** implemented and tested on synthetic inputs, with preparation additionally exercised on supplied soil/profile/heat GIS data. A complete registered flood/suitability input set remains outstanding. The example atlas is a software demonstration, not a thesis finding. The thesis was read as research material. Schwerdorf's original MURIEL presentation was retrieved and slides 19–20 checked; other technical/regulatory references still require primary-source verification.

The real-data configuration is [config/koeln_kalk_sri5.json](config/koeln_kalk_sri5.json): **SRI5**, **30-year return period as stated by the user**, flood input in **centimetres**, intervention threshold **≥10 cm**. Confirm the SRI/event definition against the flood provider's metadata. An SRI number is not treated as a universal return-period conversion.

## Guided QGIS setup

Install [the QGIS plugin ZIP](downloads/nbs-stage1-plugin-v0.4.zip) through **Plugins → Manage and Install Plugins → Install from ZIP**. Then open **Plugins → NbS planning → NbS Stage 1 · opportunity mapping**. Select inputs, adjust the threshold, check readiness and run. The engine is bundled; no repository path or JSON editing is needed for guided setup. See the [step-by-step user guide](docs/USER_GUIDE.md).

Version 0.3 adds grouped input checks, progress and cancellation, fast analysis without map printing, isolated unfinished runs, a searchable offline results dashboard and an evidence task register. Registered configurations preserve advanced evidence/combinations; the panel can copy them for a new threshold run. Spatial joins reuse coverage unions; MURIEL searches use indexed candidate filtering with exact geometry distances. Reasons, references and conservative missing-data treatment are preserved.

Version 0.4 adds a [documented preparation stage](docs/PREPARATION.md): read-only inventory, explicit CRS corrections, reprojection, vector clipping, native-grid preservation or configured alignment, NoData handling and a portable input-review project. Open **Prepare GIS data…** in the QGIS panel, or enable automatic preparation before screening. Incomplete attributes, physical units and engineering evidence are never invented.

## Run in this cloud environment

QGIS 3.40.6 and GDAL 3.10.3 are already available. Use the **QGIS Python interpreter**; the default virtual-environment Python does not contain PyQGIS.

```bash
cd /workspace/thesis
bash scripts/check_environment.sh
bash scripts/test.sh
QT_QPA_PLATFORM=offscreen XDG_CACHE_HOME=/tmp/thesis-qgis-cache \
  /usr/bin/python3 -m stage1 demo --muriel --directory outputs/my-first-demo
```

Each run requires a new output directory and preserves previous results. Open `outputs/my-first-demo/results/report.html`, or load `stage1.qgz` in QGIS. Choose a **map theme** to switch maps. Use **Identify Features** on the selected spatial layer and expand `explanation`: every rule reports the observed value, expected condition, status, citation, source locator/link, evidence reference, responsible party and closure action. The `decision_audit` table contains one row per rule evaluation.

The MURIEL demonstration produces **five dedicated map sheets**, `muriel_atlas.pdf`, a 23-sheet full Stage 1 atlas and decision/connection registers. Read [docs/MURIEL.md](docs/MURIEL.md) for the screening sequence and the distinction between the original presentation's >30 cm depth mask and the thesis's maximum-depth wording. Both footprint modes are implemented and explicitly registered.

## Use real data

1. Supply the SRI5 flood-depth raster and study-area polygon. A nonoverlapping polygon/grid layer with depth attributes is also supported. See [the input specification](docs/INPUTS.md).
2. Copy the real-data configuration to a new run configuration. Set paths, source metadata, scenario, units, output directory and confirmed vertical datum. Keep `profile_reviewed=false` until primary sources and local conditions have been checked.
3. Add groundwater/soil/protection/land-use and delivery evidence using ID joins, conservative polygon overlays, aligned raster sampling, or derived distance inputs. Missing data remain conditional. Ownership and combination examples are in [config/overlay_examples.json](config/overlay_examples.json).
4. Run:

   ```bash
   /usr/bin/python3 -m stage1 run config/your_run.json
   ```

5. Read the map limitations, review fail/conditional records and their closure requirements, and preserve the run manifest with its input/config/code checksums. Re-run to a new directory when data or thresholds change.

For example, changing `flood_threshold_m` from `0.10` to `0.20` changes the flood-need screen to 20 cm. It does not remove low-depth upstream source-control opportunities from the NbS analysis.

## Use QGIS Processing

In QGIS, add [scripts/qgis_stage1_processing.py](scripts/qgis_stage1_processing.py) using **Processing Toolbox → Scripts → Add Script to Toolbox**. Run **NbS Stage 1 · auditable opportunity maps**; select this repository folder and a run JSON. The algorithm creates a separate output project and preserves the current QGIS project. The script can be included as one step in a QGIS graphical model or batch run.

Alternatively, in the QGIS Python console:

```python
import sys
sys.path.insert(0, "/path/to/thesis")
from stage1.gis import run
output = run("/path/to/thesis/config/your_run.json")
```

Open the resulting project after saving your current work. On Windows/macOS use the Python environment shipped with your QGIS installation, not an unrelated `pip install qgis` environment. The atlas merger uses Poppler `pdfunite`; if unavailable, individual PDF sheets are retained.

## What is automated

| Step | Outputs / interpretation |
|---|---|
| Flood need | Original raster cells, or supplied nonoverlapping polygons; centimetres converted to metres; configurable inclusive threshold; NoData stays unknown |
| Groundwater | Preliminary risk/pathway screen; no final PASS without a specific module base; design-specific separation uses groundwater state, uncertainty and common vertical datum |
| MURIEL | Dissolved flood footprints, >2,000 m² / >0.30 m tests, receptor adjacency, municipal road exclusion, usable-space search, ≥70% retention overlap, and evidence-backed routing branches |
| NbS | Thesis palette represented by 15 explicit design variants; all applicable gates checked; reasons and references stored for every feature |
| Combinations | Declared modules, directed links, spatial allocations, source fractions, shared storage and evidence gates; separate maps preserve overlapping alternatives |
| Ownership | Municipal/private/other public/unknown area shares; mixed units and overlapping cadastral claims retained |
| Evidence | Input hashes, software versions, configuration/code hashes, run metadata and rule-level audit |

Structural proof, contamination clearance, groundwater investigation, authority approval and verified routing are **evidence inputs**, not conclusions that can be inferred from map colours. Numerical checks and GIS joins automate their application; missing proof never becomes a pass.

## Interpretation and transfer to another NRW area

Read [the rule register and methodology](docs/METHOD.md) before using a map for planning. `FAIL` takes precedence over `CONDITIONAL`, which takes precedence over `ADMISSIBLE`. An admissible record means the represented **screening** gates were evidenced, not construction permission or measured flood benefit. Non-infiltrating variants remain separate designs with their own structural, quality, outlet and maintenance gates.

The sequence, schema, rule audit and cartography are transferable. Rainfall, groundwater, parcel data, asset conditions, MURIEL criteria and authority requirements are local. A municipality mismatch without a reviewed local profile raises an error. Cologne values must not silently become NRW-wide rules.

**Stages 2 and 3 are not implemented.** Stage 2 will assess effects in Scenarify. Stage 3 will compare verified flood outcomes and lifecycle cost; the thesis currently treats heat as a separately reported co-benefit, while the user's proposed heat objective remains a decision for Stage 3. No Scenarify-ready hydraulic parameters, flood-reduction estimates, heat reductions, costs or Pareto results are invented by this stage.

The next data needed are listed in [docs/data_request.csv](docs/data_request.csv). Real groundwater admissibility cannot be established from a citywide average or an undated groundwater-depth image.

## Download the prepared demonstration

The [downloads folder](downloads/README.md) contains the full PDF atlas, five-sheet MURIEL atlas, portable QGIS ZIP package, decision register and PNG preview. Use GitHub’s **Download raw file** button on each file, or **Code → Download ZIP** for the entire repository. The files are stored with the repository and do not depend on chat download links.
