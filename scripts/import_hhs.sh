#!/usr/bin/env bash
# Copy your local HHS scripts into this repo (python files only: no data, no venv, no fonts, no workbook).
set -euo pipefail
SRC="${1:-$HOME/Projects/texas-hhs-enrollment}"
DST="$(cd "$(dirname "$0")/.." && pwd)/projects/01-hhs-anomaly-detector"
[ -d "$SRC" ] || { echo "source folder not found: $SRC"; exit 1; }
rsync -av --include='*.py' --exclude='*' "$SRC"/ "$DST"/
echo "Copied. Now run: git status, then check for secrets (see README 'Before you push')."
