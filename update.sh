#!/bin/bash
#
# Update Script für GitHub Backup System
# Dieses Script aktualisiert das Backup-System auf die neueste Version
#

set -euo pipefail

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging-Funktionen
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Header anzeigen
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}GitHub Backup System Update Script${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""

# Prüfe ob wir im richtigen Verzeichnis sind
if [ ! -f "ghbackup.py" ]; then
    log_error "Dieses Script muss im GitHub-Backup Verzeichnis ausgeführt werden!"
    exit 1
fi

# Aktuelle Branch ermitteln
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "main")
log_info "Aktueller Branch: $CURRENT_BRANCH"

# Prüfe auf uncommitted changes
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
    log_warning "Es gibt uncommitted Änderungen!"
    echo "Möchtest du fortfahren? Die Änderungen werden gestashed. (j/n)"
    read -r response
    if [[ ! "$response" =~ ^[jJyY]$ ]]; then
        log_info "Update abgebrochen."
        exit 0
    fi
    
    log_info "Stashe Änderungen..."
    git stash push -m "Auto-stash vor Update $(date +%Y%m%d_%H%M%S)"
    STASHED=true
else
    STASHED=false
fi

# Backup der aktuellen Konfiguration
if [ -f "config.yaml" ]; then
    BACKUP_NAME="config.yaml.backup_$(date +%Y%m%d_%H%M%S)"
    log_info "Erstelle Backup der Konfiguration: $BACKUP_NAME"
    cp config.yaml "$BACKUP_NAME"
fi

# Git Pull
log_info "Hole neueste Änderungen von GitHub..."
if git pull origin "$CURRENT_BRANCH"; then
    log_success "Repository erfolgreich aktualisiert!"
else
    log_error "Git pull fehlgeschlagen!"
    if [ "$STASHED" = true ]; then
        log_info "Stelle gestashte Änderungen wieder her..."
        git stash pop
    fi
    exit 1
fi

# Virtual Environment aktualisieren
if [ -d "venv" ]; then
    log_info "Aktualisiere Python-Dependencies..."
    ./venv/bin/pip install -r requirements.txt --upgrade
    log_success "Dependencies aktualisiert!"
else
    log_warning "Kein Virtual Environment gefunden. Erstelle eines mit:"
    echo "  python3 -m venv venv"
    echo "  ./venv/bin/pip install -r requirements.txt"
fi

# Berechtigungen setzen
log_info "Setze Ausführungsberechtigungen..."
chmod +x ghbackup
chmod +x webhook-backup.sh
chmod +x update.sh

# Prüfe ob neue Verzeichnisse erstellt werden müssen
for dir in backups logs; do
    if [ ! -d "$dir" ]; then
        log_info "Erstelle Verzeichnis: $dir"
        mkdir -p "$dir"
    fi
done

# Konfigurationsprüfung
if [ ! -f "config.yaml" ]; then
    log_warning "Keine config.yaml gefunden!"
    if [ -f "config.yaml.example" ]; then
        echo "Möchtest du die Beispiel-Konfiguration kopieren? (j/n)"
        read -r response
        if [[ "$response" =~ ^[jJyY]$ ]]; then
            cp config.yaml.example config.yaml
            log_success "config.yaml aus Beispiel erstellt. Bitte anpassen!"
        fi
    fi
fi

# Wenn Änderungen gestashed wurden, frage ob sie wiederhergestellt werden sollen
if [ "$STASHED" = true ]; then
    echo ""
    log_info "Es wurden Änderungen gestashed."
    echo "Möchtest du die gestashten Änderungen wiederherstellen? (j/n)"
    read -r response
    if [[ "$response" =~ ^[jJyY]$ ]]; then
        if git stash pop; then
            log_success "Gestashte Änderungen wiederhergestellt!"
        else
            log_error "Fehler beim Wiederherstellen der gestashten Änderungen!"
            log_info "Verwende 'git stash list' und 'git stash pop' manuell."
        fi
    else
        log_info "Gestashte Änderungen bleiben im Stash."
        log_info "Verwende 'git stash list' zum Anzeigen und 'git stash pop' zum Wiederherstellen."
    fi
fi

# Zeige Änderungen
echo ""
log_info "Zeige die letzten Commits:"
git log --oneline -5

# Status ausgeben
echo ""
log_success "Update abgeschlossen!"
echo ""
echo "Nächste Schritte:"
echo "1. Prüfe die Konfiguration in config.yaml"
echo "2. Teste die Funktionalität mit: ./ghbackup status"
echo "3. Bei Problemen prüfe die Logs in logs/"
echo ""

# Prüfe ob dies auf einem Server läuft (z.B. pixel-hotel)
if [ -f "/home/hotel/github-webhook/webhook.sh" ]; then
    log_info "Webhook-Integration erkannt!"
    echo "Denke daran, den Webhook-Service neu zu starten wenn nötig:"
    echo "  cd /home/hotel/github-webhook && ./webhook.sh stop && ./webhook.sh start"
fi