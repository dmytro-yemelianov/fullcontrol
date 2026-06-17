#!/usr/bin/env bash
# Rebuild the FullControl wheel that the Pyodide playground loads.
# The wheel is committed so the page deploys to static hosting (Cloudflare Pages) with no build
# step; re-run this whenever the library changes. Requires: pip install build.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$here/../.."

rm -f "$here"/fullcontrol-*.whl
python -m build --wheel --outdir "$here" "$repo"
# keep only the wheel (drop any stray sdist), report
ls -1 "$here"/fullcontrol-*.whl
echo "wheel staged in web/playground/ ($(du -h "$here"/fullcontrol-*.whl | cut -f1))"
