# Stage 1 v0.4: preparation and guided QGIS workflow

Start with the **[QGIS plugin ZIP](nbs-stage1-plugin-v0.4.zip)**. Open it on GitHub and select **Download raw file**. In QGIS 3.40+, choose **Plugins → Manage and Install Plugins → Install from ZIP**. Enable the plugin and open **Plugins → NbS planning → NbS Stage 1 · opportunity mapping**.

The plugin bundles the engine. Use **Prepare GIS data…** to check/correct documented CRSs, clip vectors and align rasters. Native flood-grid preparation is also available before screening. Select input layers, set the threshold, check readiness and run. See the **[step-by-step user guide](../docs/USER_GUIDE.md)** and [validation/performance evidence](../docs/VALIDATION.md).

| File | Contents | Size |
|---|---|---|
| [Installable plugin](nbs-stage1-plugin-v0.4.zip) | Native QGIS panel and complete engine | See checksums |
| [Complete workflow package](nbs-stage1-qgis.zip) | Source, plugin, tests, example inputs and portable QGIS results | 12.1 MB |
| [Complete atlas](stage1-atlas-including-muriel.pdf) | 23 A3 sheets, including five MURIEL sheets | 5.3 MB |
| [MURIEL atlas](muriel-screening-atlas.pdf) | Five dedicated screening sheets | 1.4 MB |
| [Decision register](muriel-decisions.csv) | MURIEL rule decisions, reasons and references | 51 KB |
| [Map preview](muriel-priority-preview.png) | MURIEL priority sheet | 279 KB |
| [Preparation panel preview](preparation-panel-preview.png) | CRS, clipping and grid settings | See checksums |
| [Setup panel preview](qgis-setup-preview.png) | Actual native QGIS interface | 119 KB |
| [Results dashboard preview](results-dashboard-preview.png) | Actual offline report | 129 KB |

For the example, extract `nbs-stage1-qgis.zip` and open `thesis-stage1-muriel/example/results/stage1.qgz` or `report.html`. Keep the folders together so relative paths resolve. Use **Code → Download ZIP** on this branch to download the entire repository.

**Example maps are synthetic demonstrations, not findings for Köln-Kalk.** Actual study-area data still need to be supplied. Missing evidence remains conditional. Stage 2 hydraulic simulation and Stage 3 Pareto analysis are separate work.

Exact byte sizes and SHA-256 hashes are in [SHA256SUMS.json](SHA256SUMS.json). Files are stored in Git and do not rely on a running cloud environment or chat file viewer.

Read the [preparation guide](../docs/PREPARATION.md). User-supplied GIS files and prepared real-data outputs are not included in these downloads. The example bundle contains only generated synthetic fixtures. The older v0.3 plugin is retained as a historical package.
