# GitHub Backup System

Ein robustes Backup-System für GitHub-Repositories, das sowohl Code als auch Metadaten sichert.

## Funktionen

- **Vollständige Git-Backups**: Alle Branches, Tags und Commit-Historie
- **Metadaten-Sicherung**: Issues, Pull Requests, Releases
- **Multi-Account-Support**: Mehrere GitHub-Accounts in einer Konfiguration
- **SSH-Authentifizierung**: Nutzt vorhandene SSH-Keys (kein Token nötig!)
- **Inkrementelle Backups**: Nur neue Änderungen werden geholt
- **Automatische Snapshots**: Bei kritischen Events (force-push, branch-delete)
- **Einfache Wiederherstellung**: Repositories komplett wiederherstellen

## Installation

```bash
# Repository klonen
git clone <dieses-repo>
cd github-backups

# Virtual Environment erstellen
python3 -m venv venv

# Dependencies installieren
./venv/bin/pip install -r requirements.txt

# Konfiguration erstellen
cp config.yaml.example config.yaml
# Bearbeite config.yaml mit deinen GitHub-Account-Namen
```

## Konfiguration

Die `config.yaml` benötigt nur deinen GitHub-Account-Namen:

```yaml
accounts:
  - name: SteffenBiz
    use_ssh: true  # SSH-Authentifizierung (empfohlen)

settings:
  keep_snapshots_days: 30
  log_max_size_mb: 100
```

## Verwendung

### Einzelnes Repository backuppen
```bash
./ghbackup backup SteffenBiz Repository-Name
```

### Alle Repositories eines Accounts
```bash
./ghbackup backup SteffenBiz --all
```

### Backup-Status anzeigen
```bash
./ghbackup status
```

### Repository wiederherstellen
```bash
./ghbackup restore SteffenBiz Repository-Name /pfad/zum/ziel
```

## Webhook-Integration

Das System arbeitet perfekt mit dem Github-Webhook zusammen. Hier konkrete Beispiele für die `webhook.json`:

### Basis-Integration
```json
{
  "repository_commands": {
    "SteffenBiz/MeinRepo": {
      "refs/heads/main": "cd ~/github-backups && ./ghbackup backup SteffenBiz MeinRepo --event push"
    }
  }
}
```

### Automatische Snapshots bei kritischen Branches
```json
{
  "repository_commands": {
    "SteffenBiz/Produktion": {
      "refs/heads/main": "cd ~/github-backups && ./ghbackup backup SteffenBiz Produktion --event force-push",
      "refs/heads/develop": "cd ~/github-backups && ./ghbackup backup SteffenBiz Produktion",
      "refs/heads/hotfix/*": "cd ~/github-backups && ./ghbackup backup SteffenBiz Produktion --event force-push"
    }
  }
}
```

### Multi-Repository Setup
```json
{
  "repository_commands": {
    "SteffenBiz/Website": {
      "refs/heads/main": "cd ~/github-backups && ./ghbackup backup SteffenBiz Website --event push && echo 'Website backup completed'"
    },
    "SteffenBiz/API": {
      "refs/heads/main": "cd ~/github-backups && ./ghbackup backup SteffenBiz API --event push && echo 'API backup completed'"
    },
    "SteffenBiz/Private-Docs": {
      "refs/heads/main": "cd ~/github-backups && ./ghbackup backup SteffenBiz Private-Docs --event push"
    }
  }
}
```

### Erweiterte Integration mit Backup-Wrapper
Erstelle ein Wrapper-Script `backup-on-push.sh`:

```bash
#!/bin/bash
# backup-on-push.sh
REPO=$1
EVENT=${2:-push}

cd ~/github-backups

# Backup durchführen
./ghbackup backup SteffenBiz "$REPO" --event "$EVENT"

# Optional: Bei Erfolg eine Benachrichtigung
if [ $? -eq 0 ]; then
    echo "[$(date)] Backup von $REPO erfolgreich"
else
    echo "[$(date)] FEHLER: Backup von $REPO fehlgeschlagen" >&2
fi
```

Dann in `webhook.json`:
```json
{
  "repository_commands": {
    "SteffenBiz/MeinRepo": {
      "refs/heads/main": "~/backup-on-push.sh MeinRepo force-push",
      "refs/heads/develop": "~/backup-on-push.sh MeinRepo push"
    }
  }
}
```

### Wichtige Hinweise für Webhook-Integration:
- Commands haben 5 Minuten Timeout (in webhook.json konfigurierbar)
- Bei kritischen Events (`force-push`, `branch-delete`, `tag-delete`) werden automatisch Snapshots erstellt
- Die Webhook nutzt ein Deployment-Lock - parallele Backups desselben Repos werden verhindert
- Alle Ausgaben landen im Webhook-Log (`logs/webhook.log`)

### Mitgelieferte Webhook-Dateien:
- `webhook-backup.sh` - Fertiges Wrapper-Script für Webhook-Integration
- `webhook-config-example.json` - Beispiel-Konfiguration für deine Repositories

## Verzeichnisstruktur

```
backups/
└── AccountName/
    └── Repository-Name/
        ├── repo.git/       # Bare Git Repository
        ├── metadata/       # JSON-Dateien mit GitHub-Daten
        ├── snapshots/      # Zeitpunkt-Backups bei kritischen Events
        └── status.json     # Letzter Backup-Status
```

## Logs

- Logs werden in `logs/backup.log` geschrieben
- Automatische Rotation bei 100MB
- Alte Logs werden als `backup.log.old` gespeichert

## Voraussetzungen

- Python 3.6+
- Git
- GitHub CLI (`gh`) - für API-Zugriffe ohne Token
- SSH-Key für GitHub konfiguriert

## Wiederherstellung

Bei der Wiederherstellung wird das Git-Repository vollständig wiederhergestellt. Metadaten (Issues, PRs) werden im Ordner `.github-backup-metadata` gespeichert und müssen bei Bedarf manuell zu GitHub importiert werden.

## Fehlerbehandlung

- Bei fehlgeschlagenen Backups wird der Fehler geloggt, aber andere Repositories werden weiter gesichert
- Fehlende Releases sind kein Fehler (viele Repos haben keine)
- Das System ist resilient gegen temporäre Netzwerkprobleme