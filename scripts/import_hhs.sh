#!/usr/bin/env bash
# Copy your local HHS python files into this repo, minus the held-back toolkit files.
set -euo pipefail
SRC="${1:-$HOME/Projects/texas-hhs-enrollment}"
DST="$(cd "$(dirname "$0")/.." && pwd)/projects/01-hhs-anomaly-detector"
[ -d "$SRC" ] || { echo "source folder not found: $SRC"; exit 1; }
for f in "$SRC"/*.py; do
  name="$(basename "$f")"
  case "$name" in
    build_hhs_canvas.py|title_glyphs.py|measure.py|hhs_geom_calcs.py) echo "held back: $name"; continue ;;
  esac
  cp "$f" "$DST/" && echo "copied:    $name"
done
