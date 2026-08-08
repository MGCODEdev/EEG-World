#!/bin/bash
set -euo pipefail

# Lädt ausschließlich den Quellcode der iOS-App. Keine Datenbank, .env,
# Rechnungen, Verträge oder sonstigen Produktivdaten werden übertragen.
SSH_TARGET="${1:-root@195.201.168.145}"
REMOTE_SOURCE="/var/www/eeg/ios/EEGMemberApp/"
DESTINATION_ROOT="${2:-$HOME/Developer}"
STAMP="$(date '+%Y%m%d-%H%M%S')"
DESTINATION="$DESTINATION_ROOT/EEGMemberApp-$STAMP"

for command_name in ssh rsync; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Fehler: $command_name ist auf diesem Mac nicht verfügbar."
        exit 1
    fi
done

mkdir -p "$DESTINATION_ROOT"
if [ -e "$DESTINATION" ]; then
    echo "Fehler: Ziel existiert bereits: $DESTINATION"
    exit 1
fi
mkdir "$DESTINATION"

echo "Lade iOS-Projekt nach $DESTINATION …"
rsync -az --checksum --progress \
    -e "ssh -o StrictHostKeyChecking=accept-new" \
    --exclude '.DS_Store' \
    --exclude 'DerivedData/' \
    --exclude 'build/' \
    --exclude '.build/' \
    --exclude 'xcuserdata/' \
    "$SSH_TARGET:$REMOTE_SOURCE" "$DESTINATION/"

if [ ! -f "$DESTINATION/project.yml" ] || [ ! -d "$DESTINATION/EEGMemberApp" ]; then
    echo "Fehler: Der Download ist unvollständig. Ziel bleibt zur Prüfung erhalten:"
    echo "$DESTINATION"
    exit 1
fi

echo "Download vollständig."
echo "Apple-Team: LQFUQM34Z5"
echo "Bundle-ID: at.eeg.trabocherstrasse.member"

if ! command -v xcodegen >/dev/null 2>&1; then
    if command -v brew >/dev/null 2>&1; then
        echo "XcodeGen fehlt und wird jetzt über Homebrew installiert …"
        brew install xcodegen
    else
        echo "XcodeGen fehlt und Homebrew ist nicht installiert."
        echo "Installiere bitte zuerst Homebrew von https://brew.sh und starte dieses Skript erneut."
        exit 1
    fi
fi

echo "Erzeuge Xcode-Projekt …"
(cd "$DESTINATION" && xcodegen generate)
echo "Öffne Xcode …"
open "$DESTINATION/EEGMemberApp.xcodeproj"

echo
echo "Projektordner: $DESTINATION"
