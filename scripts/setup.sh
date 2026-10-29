#!/usr/bin/env sh
set -eu
SHOWRIG_SOURCE=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
command -v python3 >/dev/null 2>&1 || { echo 'Install Python 3.11 or newer, then run this script again.'; exit 1; }
python3 -m venv "$SHOWRIG_SOURCE/.venv"
SHOWRIG_PYTHON="$SHOWRIG_SOURCE/.venv/bin/python"
if [ -d "$SHOWRIG_SOURCE/runtime/wheels" ]; then
  "$SHOWRIG_PYTHON" -m pip install --no-index --find-links "$SHOWRIG_SOURCE/runtime/wheels" "$SHOWRIG_SOURCE"
else
  echo 'Installing Showrig Python dependencies. This setup step needs a connection.'
  "$SHOWRIG_PYTHON" -m pip install "$SHOWRIG_SOURCE"
fi
if [ "${1:-}" = '--voices' ]; then
  "$SHOWRIG_PYTHON" -m showrig setup --install-voices
fi
echo 'Showrig installed. Add native video tools using Setup & extras, then run ./scripts/start-showrig.sh.'
