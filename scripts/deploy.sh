#!/bin/bash
# Copy the code from the main machine to the Mac mini and update dependencies.
# Usage: ./scripts/deploy.sh <ssh-host> [remote-dir]       e.g. ./scripts/deploy.sh macmini.local
# Restarts the LaunchAgent if it is installed. Never touches ~/openholter-data.
set -euo pipefail
HOST="${1:?anna SSH-kohde, esim. macmini.local}"
DIR="${2:-openholter}"
cd "$(dirname "$0")/.."

# build stamp shown in the UI footer: which version is running on the Mac mini
date +%Y%m%d.%H%M > openholter/BUILD
trap 'rm -f openholter/BUILD' EXIT

rsync -az --delete \
  --exclude '/.*/' --exclude __pycache__ --exclude '*.egg-info' \
  ./ "$HOST:$DIR/"

ssh "$HOST" bash -s -- "$DIR" <<'EOF'
set -euo pipefail
export PATH="/Library/Frameworks/Python.framework/Versions/Current/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
cd "$HOME/$1"
if [ ! -x .venv/bin/python ]; then
  PY=$(command -v python3.12 || command -v python3.11 || command -v python3)
  echo "Luodaan virtuaaliympäristö: $PY"
  "$PY" -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e .
if launchctl print "gui/$(id -u)/fi.wilska.openholter" >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$(id -u)/fi.wilska.openholter"
  echo "Palvelu käynnistetty uudelleen."
fi
.venv/bin/python -c "import openholter, bleak, fastapi, numpy; print('ok, openholter', openholter.__version__)"
EOF
