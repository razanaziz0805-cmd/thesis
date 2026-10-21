# Transfer the thesis workflow to another area · v0.6

The engine now defaults to a **neutral study project**, rather than Kalk. This follows thesis §5.9: the sequence, records, equations and release gates transfer; local events, groundwater, thresholds, MURIEL configuration and authority decisions do not transfer automatically.

## What stays the same

| Thesis basis | Engine invariant |
|---|---|
| §5.1; §§5.5–5.6 | Planning opportunity, design/permission qualification and modelled performance remain distinct |
| §5.5.1; Table 5.4 | Need, quality, groundwater/soil, connectivity and delivery are non-compensatory gates; a benefit or preference cannot offset FAIL |
| §§5.4.2 / 5.6.2 | Module-base elevation minus design groundwater minus uncertainty, on one documented vertical datum and scenario; preliminary clearance never becomes final PASS |
| §§4.4.2 / 5.5.3 | MURIEL protects existing retention and identifies investigations; it is not infiltration or routing approval |
| §5.7.2 | Physical combinations retain source, footprint, storage, outlet and delivery accounting without double credit |
| §§5.1 / 5.7.4 | Flood remains the planning need; heat is reported separately as baseline context/co-benefit evidence |
| §§5.4.1 / 5.8.2 | Every feature has a reason, reference and evidence/next action; inputs, code, configuration and local criteria remain traceable |

NoData and unconfigured local rules remain CONDITIONAL/unknown. Known site-specific contamination or infiltration prohibitions still fail the affected pathway. A separate lined design keeps its own quality, outlet, structural and delivery checks.

## Register the new project

| Setting | Required choice |
|---|---|
| Reporting area | Actual boundary file and study-area name; contributing/hydraulic domain is a separate question |
| Governing jurisdiction | City, region or country whose registered rule profile applies; this can cover several reporting areas |
| Processing CRS | A suitable **projected CRS in metres**; there is no default EPSG:25832. Known input CRSs may populate the selection; unknown CRSs are not guessed |
| Flood scenario | Actual provider identifier and depth units (cm or m). No default SRI5 and no SRI-to-return-period conversion |
| Return period | Unknown/null until documented; no default 30 years |
| Intervention depth | Configurable project screen, initially 10 cm from the original user specification; not a universal design standard |
| Grid | Native flood-provider grid by default. Reprojection/regridding and ID changes remain documented |
| Vertical reference | Registered for height calculations; a horizontal EPSG code does not establish a height datum |
| Local rules | Generic/unconfigured, explicit Köln reference, or a cited custom profile |
| MURIEL | Optional; locally chosen criteria, jurisdiction and adoption reference, independently of local infiltration rules |

The minimum spatial inputs remain **boundary + numeric flood depth**. Add one classified surface layer for the five planning-family maps, then ownership/heat/known exclusions where available. Planning maps can run with generic rules; detailed designs stay conditional where the necessary local evidence is missing.

## Use the QGIS panel

Enter your area, event and units; select the flood layer and boundary. A suitable declared metre-based input CRS can populate the processing selection, which remains editable. Leave **Generic · local rules unconfigured** selected for initial planning. Choose a governing jurisdiction and **Load local profile…** when a profile has been registered. **Köln · thesis reference profile** is an explicit case-study option and requires the Köln governing jurisdiction.

Advanced mode retains detailed qualification and full MURIEL inputs. Its displayed MURIEL values are the Porz/Eil reference example. Edit them for the project and enter the dated local adoption reference. An unadopted or wrong-scope screen is retained as EVIDENCE_GAP, even if its spatial calculations complete. Nearby space alone never proves a safe flow route. Automatic preparation preserves a context extension at least as large as the largest registered receptor, municipal-land or destination distance.

## Register local legal/technical criteria once, then reuse them

Start from [local_profile.template.json](../config/local_profile.template.json). The profile represents the **resolved applicable rules** across national, regional, local and technical sources; the engine does not decide legal precedence between conflicting documents. Keep unresolved requirements conditional and obtain the relevant specialist/authority evidence.

- Give the profile a versioned `profile_id`, `profile_kind: "custom"`, `rule_scope`, matching `municipality` (the governing jurisdiction label), and competent `authority_label`.
- Register groundwater floor/preferred values, property/basement/asset setbacks and their mandatory-versus-recommended treatment. Null means unconfigured; zero is an explicit criterion, not a missing value.
- Set `groundwater_intermediate_action` to `FAIL`, `CONDITIONAL` or `EXCEPTION`. An exception route needs its own `groundwater_exception_fields`, whose Boolean evidence must all be documented. The Köln/DWA exception procedure is not inherited by a custom region.
- Map local protection codes in `protection_zones`: `excluded`, `outer`, `outside`, `shaft_excluded`. Generic projects do not infer restrictions just because a code is called I or II. Explicit site prohibitions can use `infiltration_prohibited`, or the planning exclusion overlay.
- Register `sewer_strip_bands` if a diameter/width rule applies. Alternatively, documented `sewer_corridor_compatible` evidence can describe an assessed surveyed corridor; a known incompatible corridor fails. The source of a setback must still be registered for numeric checks.
- Add full `references` entries with `citation`, `locator`, `url` (may be blank) and verification `status`; bind them through `rule_sources` roles `infiltration`, `groundwater`, `assets`, `roof`. References may retain additional authority/version/scope metadata in the profile snapshot.
- Mark `profile_reviewed` true only with a governing jurisdiction, dated `profile_review_ref` and cited sources for all configured local criteria. This is an evidence declaration, not a software-issued approval.

Custom criteria without governing references remain conditional. A review checkbox cannot move the Köln profile to another jurisdiction, and a custom reference cannot overwrite a built-in citation ID. The generic core uses the thesis as a methodological source; the thesis's actual title still names Köln-Kalk in the bibliography. That citation is not a geographic constraint on the workflow.

The supplied [Köln profile](../config/koeln_profile.json) preserves the thesis's provisional local/secondary-source values, including source verification limits. [koeln_kalk_sri5.json](../config/koeln_kalk_sri5.json) remains an explicitly named historical case-study configuration. It is not the default for a new area.

## CLI and reusable configuration

```bash
/usr/bin/python3 -m stage1 init project.json \
  --area "My study area" --scenario "PROVIDER_EVENT_ID" \
  --crs "EPSG:32631" --jurisdiction "My governing authority" --depth-units cm
```

EPSG:32631 here is an example for an appropriate UTM zone, not a recommended CRS for every area. Select the correct projection for the actual location. Set dataset paths/source metadata before validating/running. `init` without those flags produces an intentionally incomplete neutral template. `--profile-file local_profile.json` embeds a registered profile; `--profile koeln` explicitly selects the case-study profile.

```bash
/usr/bin/python3 -m stage1 validate project.json
/usr/bin/python3 -m stage1 run project.json
/usr/bin/python3 -m stage1 demo --planning --crs EPSG:32734 --directory outputs/generic-example
```

The last command generates an **artificial** southern-UTM example. It does not reassign a real dataset's CRS. The separate `demo --muriel` fixture retains the original local-screen example and explicit synthetic adoption metadata.

## Audit and migration

Every run writes `rule_profile.json`, with its actual jurisdiction, resolved rule values, citations, review state, flood threshold, event, return-period statement and MURIEL registration. The same context is stored in `run_manifest.json`. Active sources are written to `source_registry.csv`/GeoPackage, and custom citations are bound to their individual decisions without changing a process-global registry. Sequential projects cannot replace each other's rule citations. Geometry-based feature IDs are project-scoped; retain the run/scenario/CRS context when combining records from different areas.

Legacy configurations explicitly named `koeln_thesis_provisional_v1` retain the Köln reference values. A blank/omitted policy now means **generic**, not implicit Köln. New projects must provide a CRS, event and units. Existing MURIEL configurations without local adoption/scope evidence still calculate geometry but retain EVIDENCE_GAP until that methodological registration is supplied. Copy prior runs to a new output folder; never overwrite their audit.

Transferability is demonstrated with synthetic projects, different projected CRSs and local rule sets. It does not mean every jurisdiction's law is included, every CRS is appropriate, or city-scale hydraulic performance is validated. The 250,000-unit default guard remains; large/high-resolution studies need explicit partitioning. Stages 2 (Scenarify) and 3 (verified flood/cost portfolio comparison) remain separate work.
