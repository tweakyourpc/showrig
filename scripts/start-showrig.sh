#!/usr/bin/env sh
set -eu
SHOWRIG_SOURCE=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
SHOWRIG_PYTHON="$SHOWRIG_SOURCE/.venv/bin/python"
if [ ! -x "$SHOWRIG_PYTHON" ]; then
  echo 'Run ./scripts/setup.sh first. Starting Showrig never installs or downloads prerequisites.'
  exit 1
fi
cd "$SHOWRIG_SOURCE"
exec "$SHOWRIG_PYTHON" -m showrig web --projects "$SHOWRIG_SOURCE/films" "$@"
