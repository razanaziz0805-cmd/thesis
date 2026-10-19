# Stage 1 downloads, including MURIEL

These are **synthetic demonstrations**, not findings for Köln-Kalk. Actual study-area GIS layers have not yet been supplied. The download package contains the reusable workflow, example inputs, QGIS project, maps, decision audit, references and tests.

| File | Contents | Size |
|---|---|---|
| [Complete atlas](stage1-atlas-including-muriel.pdf) | 23 A3 sheets, including five MURIEL sheets | 5.3 MB |
| [MURIEL atlas](muriel-screening-atlas.pdf) | Five dedicated screening sheets | 1.4 MB |
| [QGIS workflow package](nbs-stage1-qgis.zip) | Source, example GIS inputs and portable QGIS results | 11.8 MB |
| [Decision register](muriel-decisions.csv) | Rule decisions, reasons and source references | 51 KB |
| [Map preview](muriel-priority-preview.png) | MURIEL priority sheet as a PNG | 279 KB |

Open a file above and use GitHub's **Download raw file** button. To download everything, use the repository's **Code → Download ZIP** option on this branch. These files are stored in Git; they do not rely on a running cloud environment or chat attachment service.

For QGIS, extract `nbs-stage1-qgis.zip` and open `thesis-stage1-muriel/example/results/stage1.qgz`. Use a map theme to choose a result and Identify Features to inspect the decisions. Keep the folder structure together so relative input paths resolve.

Checksums and exact byte sizes are in [SHA256SUMS.json](SHA256SUMS.json).

The repository's [README](../README.md), [MURIEL method](../docs/MURIEL.md) and [validation notes](../docs/VALIDATION.md) explain the interpretation and limitations.
