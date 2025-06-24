#!/bin/bash
#
# Webhook Backup Wrapper
# Dieses Script wird von der GitHub Webhook aufgerufen
#
# Verwendung: webhook-backup.sh <repo-name> [event-type]
# Beispiel: webhook-backup.sh Test-Repo push

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_NAME=$1
EVENT_TYPE=${2:-push}

# Account aus dem Repository-Namen extrahieren (falls im Format Account/Repo)
if [[ "$REPO_NAME" == *"/"* ]]; then
    ACCOUNT=$(echo "$REPO_NAME" | cut -d'/' -f1)
    REPO=$(echo "$REPO_NAME" | cut -d'/' -f2)
else
    # Standard-Account aus config.yaml verwenden
    ACCOUNT="SteffenBiz"
    REPO="$REPO_NAME"
fi

# Logging
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Webhook-Backup gestartet für $ACCOUNT/$REPO (Event: $EVENT_TYPE)"

# In Backup-Verzeichnis wechseln
cd "$SCRIPT_DIR"

# Backup durchführen
./ghbackup backup "$ACCOUNT" "$REPO" --event "$EVENT_TYPE"
BACKUP_EXIT_CODE=$?

# Ergebnis loggen
if [ $BACKUP_EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✓ Backup erfolgreich: $ACCOUNT/$REPO"
    
    # Optional: Statistik anzeigen
    if [ -f "backups/$ACCOUNT/$REPO/status.json" ]; then
        SIZE=$(cat "backups/$ACCOUNT/$REPO/status.json" | grep -o '"size": "[^"]*"' | cut -d'"' -f4)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   Größe: $SIZE"
    fi
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✗ FEHLER beim Backup von $ACCOUNT/$REPO (Exit Code: $BACKUP_EXIT_CODE)" >&2
fi

# Exit mit gleichem Code wie das Backup
exit $BACKUP_EXIT_CODE