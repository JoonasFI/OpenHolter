#!/bin/bash
# Install OpenHolter as a LaunchAgent of the logged-in user (not a LaunchDaemon:
# Bluetooth permission is per user and needs the GUI session).
# Run on the Mac mini from the project directory:  ./scripts/install-launchagent.sh
set -euo pipefail

LABEL="fi.wilska.openholter"
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$PROJECT/.venv/bin/python"
HOME_DIR="${OPENHOLTER_HOME:-$HOME/openholter-data}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

[ -x "$PY" ] || { echo "Virtuaaliympäristöä ei löydy: $PY (katso README, kohta Asennus)"; exit 1; }
mkdir -p "$HOME/Library/LaunchAgents" "$HOME_DIR/logs"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string><string>-m</string><string>openholter</string><string>run</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJECT</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OPENHOLTER_HOME</key><string>$HOME_DIR</string>
    <key>OPENHOLTER_NO_STDERR</key><string>1</string>
    <key>PATH</key><string>/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <!-- Interactive: no App Nap / timer coalescing, BLE notifications keep flowing -->
  <key>ProcessType</key><string>Interactive</string>
  <key>LimitLoadToSessionType</key><string>Aqua</string>
  <key>StandardOutPath</key><string>$HOME_DIR/logs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$HOME_DIR/logs/launchd.err.log</string>
</dict>
</plist>
EOF

DOMAIN="gui/$(id -u)"
# the project was called Hearth before 0.3: retire that agent so two collectors never compete for the strap
if launchctl print "$DOMAIN/fi.wilska.hearth" >/dev/null 2>&1; then
  launchctl bootout "$DOMAIN/fi.wilska.hearth" || true
  rm -f "$HOME/Library/LaunchAgents/fi.wilska.hearth.plist"
  echo "Vanha Hearth-palvelu poistettu."
fi
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl enable "$DOMAIN/$LABEL"
echo "Asennettu: $PLIST"
echo "Tila:      launchctl print $DOMAIN/$LABEL | head -20"
echo "Loki:      tail -f $HOME_DIR/logs/openholter.log"
