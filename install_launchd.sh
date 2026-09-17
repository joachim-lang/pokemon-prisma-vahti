#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.joachim.pokemon-scraper"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
PYTHON="$(command -v python3)"

mkdir -p "$ROOT/data"
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON}</string>
    <string>${ROOT}/scraper.py</string>
    <string>--once</string>
  </array>
  <key>StartInterval</key>
  <integer>300</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${ROOT}/data/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${ROOT}/data/launchd.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
echo "Asennettu: $PLIST"
echo "Seuraava tarkistus ajetaan heti ja sen jälkeen 5 min välein."
echo "Pysäytys: launchctl bootout gui/\$(id -u)/${LABEL}"
