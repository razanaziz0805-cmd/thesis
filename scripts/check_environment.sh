#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export QT_QPA_PLATFORM=offscreen
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/thesis-qgis-cache}"
mkdir -p "$XDG_CACHE_HOME"
QGIS_PYTHON="${QGIS_PYTHON:-/usr/bin/python3}"
"$QGIS_PYTHON" - <<'PY'
from qgis.core import Qgis
from qgis.PyQt.QtSvg import QSvgGenerator
from osgeo import gdal
import numpy
print('QGIS:', Qgis.QGIS_VERSION)
print('GDAL:', gdal.VersionInfo())
print('NumPy:', numpy.__version__)
assert gdal.GetDriverByName('GTiff')
assert gdal.GetDriverByName('GPKG')
print('GeoTIFF, GeoPackage and Qt SVG support available')
PY
if command -v pdfunite >/dev/null 2>&1; then
  printf 'PDF atlas merger: available\n'
else
  printf 'PDF atlas merger: unavailable; individual PDF sheets will be retained\n'
fi
