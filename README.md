# Transferable NbS opportunity mapping · Stage 1

A QGIS engine for the thesis workflow: flood need → preliminary pathway restrictions → NbS opportunities and MURIEL → design/combination qualification and delivery evidence. The default setup now supports **any study area with suitable input data and locally registered criteria**. Kalk is an explicit case-study configuration, not a runtime default.

**Version 0.6** separates transferable decision logic from local legal/technical values, events and coordinate systems. Read [how transfer follows the thesis](docs/TRANSFERABILITY.md) and the [short planning input table](docs/PLANNING.md). Only Stage 1 is implemented; no hydraulic, cooling, cost or Pareto result is inferred from GIS screening.

## Start in QGIS

Download the [v0.6 plugin ZIP](downloads/nbs-stage1-plugin-v0.6.zip). On GitHub select **Download raw file**, then in QGIS 3.40+ use **Plugins → Manage and Install Plugins → Install from ZIP**. Open **Plugins → NbS planning → NbS Stage 1 · opportunity mapping**. The engine is bundled; no repository path or extra server is needed.

1. Enter the study area, actual flood-provider event and depth units.
2. Select **boundary + numeric flood depth**, a suitable projected CRS in metres, and a workspace. Known input CRS metadata may populate the selection; an unknown CRS is never guessed.
3. Keep **Generic · local rules unconfigured** for the first planning maps. Add surface types, ownership, heat and known exclusions when available. Load a cited local profile when ready.
4. Check inputs, create results, open the offline report and `stage1.qgz`. Choose a map theme and use **Identify Features** for reasons, evidence, citations and next actions.

The initial 10 cm screen remains configurable and explicitly project-defined. There is **no automatic SRI5, 30-year return period, EPSG:25832 or Köln rule selection**. A specific SRI label does not establish a universal return period.

## Local rules are explicit

| Profile | Behaviour |
|---|---|
| Generic (default) | No imposed numeric local thresholds or zone-code restrictions; missing criteria stay conditional |
| Cited custom profile | Registered jurisdiction, local numbers/code mappings, rule severity, exception procedure and actual source references |
| Köln reference | Explicit thesis case-study values and their primary/secondary-source limitations; cannot be reassigned to another jurisdiction by a review checkbox |

Use [local_profile.template.json](config/local_profile.template.json) to register a reusable local profile. [koeln_profile.json](config/koeln_profile.json) and [koeln_kalk_sri5.json](config/koeln_kalk_sri5.json) remain available as named case-study material. Generic method citations retain the thesis's proper title; this does not impose its study geography.

MURIEL retains the Porz/Eil example as an optional reference preset. Local values, scope, source and adoption are registered separately. Unadopted or wrong-scope criteria remain EVIDENCE_GAP. MURIEL does not confer infiltration permission or prove routing.

## Outputs for planning and qualification

- Connected flood action areas, mapped depth/area, extent uncertainty and source-unit links.
- Five conditional NbS planning families from surface classes, with provisional water pathways and next investigations.
- Ownership shares/delivery actions and documented flood/heat overlap, retaining unknowns and conflicts.
- Preliminary groundwater/soil/protection evidence, optional full MURIEL, and 15 explicit design variants in advanced mode.
- Declared physical combination checks with source/footprint/storage accounting and no additive hydraulic-benefit assumption.
- Portable QGIS project, GeoPackage, feature reasons/references, CSV registers, offline report and optional A3 PNG/PDF sheets.
- `rule_profile.json` plus input/configuration/code hashes and software versions, documenting the actual governing criteria used.

Every retained planning concept is **CONDITIONAL** until qualified. Known incompatible pathways remain FAIL; a lined alternative has its own checks. NoData and absent evidence never become a pass. Heat is context/co-benefit evidence, not an invented cooling coefficient or a means of offsetting a hard failure.

## Preparation and larger inputs

Automatic preparation registers source CRS, clips vectors, preserves the flood native grid by default, handles NoData and creates an input-review project. Explicit CRS correction requires evidence; source files are preserved. See [PREPARATION.md](docs/PREPARATION.md). The current 250,000-unit default guard remains: larger/high-resolution studies need a documented partition strategy, not silent coarsening.

## Run from source

Use QGIS's Python environment. In this cloud environment:

```bash
cd /workspace/thesis
bash scripts/check_environment.sh
bash scripts/test.sh
/usr/bin/python3 -m stage1 init project.json \
  --area "My area" --scenario "PROVIDER_EVENT_ID" \
  --crs "EPSG:32631" --jurisdiction "My authority" --depth-units cm
/usr/bin/python3 -m stage1 validate project.json
/usr/bin/python3 -m stage1 run project.json
```

Choose a CRS appropriate to the actual location; EPSG:32631 is just an example. Supply dataset paths/source metadata before validation. Use `--profile-file local_profile.json` for registered local criteria. Runs preserve previous folders; cancellation/failure does not publish unfinished results.

For a neutral software demonstration:

```bash
/usr/bin/python3 -m stage1 demo --planning --crs EPSG:32734 --directory outputs/transfer-demo
```

The generated data and maps are synthetic. The separate `demo --muriel` retains the thesis's explicit local-screen fixture. QGIS Processing/model integration remains available through [scripts/qgis_stage1_processing.py](scripts/qgis_stage1_processing.py).

See [USER_GUIDE.md](docs/USER_GUIDE.md), [INPUTS.md](docs/INPUTS.md), [METHOD.md](docs/METHOD.md), [MURIEL.md](docs/MURIEL.md), and [validation evidence](docs/VALIDATION.md). The [downloads folder](downloads/README.md) supplies the installable plugin and a portable synthetic example. Private uploaded GIS files and prepared real-data outputs are excluded from public packages. Actual legal applicability, site clearance and hydraulic performance still require their corresponding evidence.
