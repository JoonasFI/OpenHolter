#!/bin/bash
# Stop and remove the OpenHolter LaunchAgent. Recorded data is not touched.
set -euo pipefail
LABEL="fi.wilska.openholter"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Poistettu. Data on edelleen hakemistossa ${OPENHOLTER_HOME:-$HOME/openholter-data}."
