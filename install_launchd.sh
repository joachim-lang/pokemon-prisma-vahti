#!/bin/zsh
set -euo pipefail

LABEL="com.joachim.pokemon-scraper"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
rm -f "$PLIST"
echo "Mac-vahti poistettu. Seuranta on vain GitHub Actionsissa (julkinen repo, 5 min cron + 15 s pollaus jobin sisällä)."
echo "Läppärin ei tarvitse olla auki."
