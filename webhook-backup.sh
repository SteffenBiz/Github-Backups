#!/bin/bash
#
# Webhook Backup Wrapper - Produktionsreife Version
# Dieses Script wird vom externen Webhook-Server aufgerufen
#
# Verwendung: webhook-backup.sh <repo-name> [event-type] [signature] [secret]
# Beispiel: webhook-backup.sh Test-Repo push sha256=abc123... mysecret
#
# Sicherheitsverbesserungen:
# - Eingabevalidierung für alle Parameter
# - Keine direkte Verwendung von Variablen in Befehlen
# - Webhook-Signatur-Verifizierung
# - Sichere Pfadbehandlung

set -euo pipefail  # Exit on error, undefined variables, pipe failures

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_NAME="${1:-}"
EVENT_TYPE="${2:-push}"
SIGNATURE="${3:-}"
SECRET="${4:-}"

# Logging-Funktion
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Fehler-Handler
error_exit() {
    log "ERROR: $1" >&2
    exit 1
}

# Eingabevalidierung
validate_input() {
    local input="$1"
    local name="$2"
    
    # Prüfe auf leere Eingabe
    if [[ -z "$input" ]]; then
        error_exit "$name darf nicht leer sein"
    fi
    
    # Prüfe auf gefährliche Zeichen (Whitelist-Ansatz)
    if ! [[ "$input" =~ ^[a-zA-Z0-9._/-]+$ ]]; then
        error_exit "Ungültige Zeichen in $name: $input"
    fi
    
    # Prüfe auf Path Traversal
    if [[ "$input" == *".."* ]] || [[ "$input" == "/"* ]] || [[ "$input" == *"\\"* ]]; then
        error_exit "Path traversal Versuch in $name erkannt: $input"
    fi
    
    # Maximale Länge
    if [[ ${#input} -gt 100 ]]; then
        error_exit "$name ist zu lang (max 100 Zeichen): $input"
    fi
}

# Validiere Repository-Name
if [[ -z "$REPO_NAME" ]]; then
    error_exit "Repository-Name ist erforderlich"
fi

validate_input "$REPO_NAME" "Repository-Name"
validate_input "$EVENT_TYPE" "Event-Type"

# Account aus dem Repository-Namen extrahieren (falls im Format Account/Repo)
if [[ "$REPO_NAME" == *"/"* ]]; then
    # Sichere Extraktion mit Parameter Expansion
    ACCOUNT="${REPO_NAME%%/*}"
    REPO="${REPO_NAME#*/}"
    
    # Nochmals validieren nach Aufteilung
    validate_input "$ACCOUNT" "Account-Name"
    validate_input "$REPO" "Repository-Name (nach Split)"
else
    # Standard-Account aus config.yaml verwenden
    # Kann über Umgebungsvariable DEFAULT_ACCOUNT überschrieben werden
    ACCOUNT="${DEFAULT_ACCOUNT:-SteffenBiz}"
    REPO="$REPO_NAME"
fi

# Webhook-Signatur verifizieren (falls vorhanden)
if [[ -n "$SIGNATURE" ]] && [[ -n "$SECRET" ]]; then
    log "Verifiziere Webhook-Signatur..."
    
    # Verwende Python-Script für Signatur-Verifizierung
    # (Da bash keine eingebaute HMAC-SHA256 Unterstützung hat)
    VERIFY_RESULT=$("$SCRIPT_DIR/ghbackup" verify-webhook \
        --body "$REPO_NAME:$EVENT_TYPE" \
        --signature "$SIGNATURE" \
        --secret "$SECRET" 2>&1) || true
    
    if [[ "$VERIFY_RESULT" != *"Signature valid: True"* ]]; then
        error_exit "Webhook-Signatur-Verifizierung fehlgeschlagen"
    fi
    
    log "✓ Webhook-Signatur verifiziert"
fi

# Logging
log "Webhook-Backup gestartet für $ACCOUNT/$REPO (Event: $EVENT_TYPE)"

# In Backup-Verzeichnis wechseln
cd "$SCRIPT_DIR" || error_exit "Konnte nicht in Script-Verzeichnis wechseln"

# Backup durchführen mit Timeout
timeout 600 ./ghbackup backup "$ACCOUNT" "$REPO" --event "$EVENT_TYPE"
BACKUP_EXIT_CODE=$?

# Ergebnis loggen
if [ $BACKUP_EXIT_CODE -eq 0 ]; then
    log "✓ Backup erfolgreich: $ACCOUNT/$REPO"
    
    # Optional: Statistik anzeigen (sicher)
    STATUS_FILE="backups/$ACCOUNT/$REPO/status.json"
    if [ -f "$STATUS_FILE" ]; then
        # Sichere JSON-Extraktion mit Python
        SIZE=$(python3 -c "
import json
try:
    with open('$STATUS_FILE', 'r') as f:
        data = json.load(f)
        print(data.get('size', 'unknown'))
except:
    print('unknown')
" 2>/dev/null) || SIZE="unknown"
        
        log "  Größe: $SIZE"
    fi
else
    error_exit "Backup fehlgeschlagen für $ACCOUNT/$REPO (Exit Code: $BACKUP_EXIT_CODE)"
fi

# Erfolg
exit 0