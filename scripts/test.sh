#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export QT_QPA_PLATFORM=offscreen
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/thesis-qgis-cache}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/thesis-qgis-runtime}"
mkdir -p "$XDG_CACHE_HOME" "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
QGIS_PYTHON="${QGIS_PYTHON:-/usr/bin/python3}"
"$QGIS_PYTHON" -m unittest discover -s tests -v
