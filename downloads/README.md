# Stage 1 v0.5 · small-input urban planning

Download the **[v0.5 QGIS plugin](nbs-stage1-plugin-v0.5.zip)**. On its GitHub file page, select **Download raw file**. In QGIS 3.40+, install it through **Plugins → Manage and Install Plugins → Install from ZIP** and enable NbS Stage 1 Opportunity Mapping.

The default panel starts with **two spatial datasets: flood depth and study boundary**. Surface types, ownership, heat and known infiltration exclusions are optional additions. It produces flood action areas, conditional NbS concepts, references and next actions. Advanced mode preserves detailed design qualification, MURIEL and physical combination checks. [Read the short planning guide and input table](../docs/PLANNING.md).

| Download | Contents |
|---|---|
| [Installable plugin v0.5](nbs-stage1-plugin-v0.5.zip) | Default planning panel, automatic GIS preparation and advanced engine |
| [Planning example and complete workflow v0.5](nbs-stage1-planning-v0.5.zip) | Source, plugin, guides, tests, synthetic inputs and portable QGIS/report results |
| [Planning atlas](stage1-planning-atlas.pdf) | Ten A3 example map sheets |
| [Planning action-area register](planning-shortlist.csv) | Synthetic discussion areas, ownership shares, heat context, reasons and next actions |
| [Planning map preview](planning-map-preview.png) | Flood action-area sheet |
| [Planning interface preview](planning-interface-preview.png) | Actual simpler QGIS panel |
| [Planning report preview](planning-report-preview.png) | Actual offline planning brief |
| [MURIEL atlas](muriel-screening-atlas.pdf) | Five dedicated local-screen example sheets |
| [MURIEL rule decisions](muriel-decisions.csv) | Reasons and references for the MURIEL demonstration |
| [Earlier complete MURIEL workflow](nbs-stage1-qgis.zip) | Historical v0.4 package and its 23-sheet example |
| [Earlier complete atlas](stage1-atlas-including-muriel.pdf) | Historical 23-sheet example, including five MURIEL sheets |

For the new example, extract `nbs-stage1-planning-v0.5.zip` and open `thesis-stage1-planning/example/results/stage1.qgz` or `report.html`. Keep the extracted folders together. Select QGIS map themes and use Identify Features for the reasoning. Install the plugin ZIP inside the extracted folder separately.

**All example maps are synthetic demonstrations, not findings for Köln-Kalk.** Actual SRI5 numeric flood data remain outstanding. Planning concepts are conditional; design, authority evidence and hydraulic modelling remain subsequent work. User-supplied GIS data and prepared real-data outputs are excluded from every download.

Sizes and SHA-256 hashes are in [SHA256SUMS.json](SHA256SUMS.json). These repository files do not depend on a cloud session or chat file viewer. **Code → Download ZIP** on this branch downloads the whole repository. Earlier v0.3/v0.4 plugin packages and screenshots are retained as historical artifacts. [Validation details](../docs/VALIDATION.md).
