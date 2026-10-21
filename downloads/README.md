# Stage 1 v0.6 · transferable thesis workflow

Start with the **[v0.6 QGIS plugin](nbs-stage1-plugin-v0.6.zip)**. On GitHub choose **Download raw file**, then install the intact ZIP through QGIS 3.40+ **Plugins → Manage and Install Plugins → Install from ZIP**.

The engine now opens a neutral project. Choose the area's actual event, depth units and suitable projected CRS in metres. Generic local rules stay conditional; load a cited profile for jurisdiction-specific checks. The Köln thesis profile remains an explicit reference option. MURIEL criteria need local scope/adoption and preserve their own actual sources.

| Download | Contents |
|---|---|
| [Installable plugin v0.6](nbs-stage1-plugin-v0.6.zip) | Neutral setup, local profiles, automatic preparation, planning and advanced qualification |
| [Complete transferable workflow/example v0.6](nbs-stage1-transferable-v0.6.zip) | Plugin, source, tests, guides, templates and a portable synthetic southern-UTM QGIS/report example |
| [Neutral example atlas](stage1-transferable-atlas.pdf) | Ten A3 sheets in EPSG:32734, with no inferred local rules or return period |
| [Neutral interface preview](transferable-interface-preview.png) | Actual QGIS panel |
| [Neutral report preview](transferable-report-preview.png) | Actual offline planning brief |
| [Neutral map preview](transferable-map-preview.png) | Example flood action-area sheet |
| [Explicit local-screen MURIEL atlas](muriel-screening-atlas.pdf) | Historical synthetic Porz/Eil-criteria example; retained as reference material |

Extract the v0.6 workflow ZIP and open `thesis-stage1-transferable/example/results/stage1.qgz` or `report.html`. Keep the extracted folders together. `rule_profile.json` documents the actual local-criteria state used in the example. Use QGIS map themes and Identify Features to read reasons, source references and next actions.

See the **[transferability guide](../docs/TRANSFERABILITY.md)**, [short planning input table](../docs/PLANNING.md), [user guide](../docs/USER_GUIDE.md) and [validation evidence](../docs/VALIDATION.md).

All example observations, ownership and outcomes are **synthetic software fixtures**, not results for a real area. Private uploaded GIS data and prepared real-data outputs are excluded. Stages 2/3 hydraulic performance and verified portfolio comparison remain separate work.

[SHA256SUMS.json](SHA256SUMS.json) records exact byte sizes and hashes. Files are stored in Git and do not depend on a running chat/cloud file viewer. Earlier v0.3–v0.5 packages, atlases and previews are retained as historical artifacts. **Code → Download ZIP** on this branch downloads the repository.
