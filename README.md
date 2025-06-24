# GitHub Backup System

Ein robustes, produktionsreifes Backup-System für GitHub-Repositories mit umfassenden Sicherheitsverbesserungen.

## Features

- **Vollständige Git-Backups**: Alle Branches, Tags und die komplette Commit-Historie
- **Metadaten-Backup**: Issues, Pull Requests, Releases und Repository-Informationen
- **Multi-Account-Support**: Mehrere GitHub-Accounts in einer Konfiguration
- **SSH-Authentifizierung**: Nutzt bestehende SSH-Keys (kein Token erforderlich)
- **GitHub CLI Support**: Alternativ Nutzung von `gh` CLI für tokenlose Authentifizierung
- **Inkrementelle Backups**: Holt nur neue Änderungen ab
- **Automatische Snapshots**: Erstellt Snapshots bei kritischen Events (force-push, branch-delete, tag-delete)
- **Einfache Wiederherstellung**: Vollständige Repository-Wiederherstellung mit einem Befehl
- **Webhook-Integration**: Arbeitet mit externem Webhook-Server für event-gesteuerte Backups

## Sicherheitsfeatures

- **Eingabevalidierung**: Umfassende Validierung aller User-Inputs
- **Command Injection Schutz**: Sichere Verarbeitung von Shell-Befehlen
- **Path Traversal Schutz**: Verhindert Zugriff außerhalb des Backup-Verzeichnisses
- **Webhook-Signatur-Verifizierung**: HMAC-SHA256 Verifizierung für Webhooks
- **Sichere Token-Handhabung**: Keine Token in URLs oder Logs
- **Transactional Safety**: Atomare Backup-Operationen mit Rollback
- **Rate Limiting**: Respektiert GitHub API Rate Limits
- **Timeout-Schutz**: Alle externen Operationen mit Timeout
- **Retry-Logik**: Automatische Wiederholung bei Netzwerkfehlern

## Voraussetzungen

- Python 3.6+
- Git
- GitHub CLI (`gh`) - für API-Zugriff ohne Token
- SSH-Key konfiguriert für GitHub (empfohlen)

## Installation

1. Repository klonen:
   ```bash
   git clone https://github.com/SteffenBiz/Github-Backups.git
   cd Github-Backups
   ```

2. Virtual Environment erstellen:
   ```bash
   python3 -m venv venv
   ./venv/bin/pip install -r requirements.txt
   ```

3. Konfiguration anpassen:
   ```bash
   cp config.yaml.example config.yaml
   # Editiere config.yaml mit deinen GitHub-Account-Namen
   ```

4. SSH-Zugriff testen:
   ```bash
   ssh -T git@github.com
   ```

5. GitHub CLI authentifizieren (optional):
   ```bash
   gh auth login
   gh auth status
   ```

## Verwendung

### Einzelnes Repository sichern
```bash
./ghbackup backup <account> <repository>

# Beispiel:
./ghbackup backup SteffenBiz Test-Repo
```

### Alle Repositories eines Accounts sichern
```bash
./ghbackup backup <account> --all

# Beispiel:
./ghbackup backup SteffenBiz --all
```

### Alle konfigurierten Accounts sichern
```bash
./ghbackup backup-all
```

### Backup-Status anzeigen
```bash
./ghbackup status
```

### Repository wiederherstellen
```bash
./ghbackup restore <account> <repository> <target-path>

# Beispiel:
./ghbackup restore SteffenBiz Test-Repo /home/user/restored-repo
```

### Webhook-Integration

Das Backup-System arbeitet mit dem separaten [Github-Webhook](https://github.com/SteffenBiz/Github-Webhook) Server zusammen, der bereits auf deinem Server läuft. Das Backup-System selbst hat keine eigene Webhook-Funktionalität.

```bash
# Wird vom Webhook-Server aufgerufen:
./webhook-backup.sh <repository> <event-type> [signature] [secret]

# Beispiel:
./webhook-backup.sh SteffenBiz/Test-Repo push
```

Die `webhook-config.json` gehört zum Webhook-Server und definiert, welche Backup-Befehle bei GitHub-Events ausgeführt werden.

## Konfiguration

Die Konfiguration erfolgt über `config.yaml`:

```yaml
accounts:
  - name: YourGitHubUsername
    use_ssh: true  # Empfohlen: SSH für git Operationen

webhook:
  secret: ${WEBHOOK_SECRET}  # Für Signatur-Verifizierung

settings:
  keep_snapshots_days: 30
  log_max_size_mb: 100
  git_timeout: 300
  api_timeout: 30
  max_retries: 3
```

### Umgebungsvariablen

- `WEBHOOK_SECRET`: Secret für GitHub Webhook-Signatur-Verifizierung
- `GITHUB_TOKEN_*`: Optional für API-Zugriff (wenn kein SSH/gh verwendet wird)

## Sicherheitshinweise

1. **SSH-Authentifizierung verwenden**: Vermeidet Token in der Konfiguration
2. **Webhook-Secret setzen**: Nutze ein starkes, zufälliges Secret
3. **Berechtigungen prüfen**: Stelle sicher, dass Backup-Verzeichnisse geschützt sind
4. **Logs überwachen**: Regelmäßig Logs auf Fehler prüfen
5. **Backups verifizieren**: Teste regelmäßig die Wiederherstellung

## Verzeichnisstruktur

```
backups/
└── AccountName/
    └── Repository-Name/
        ├── repo.git/       # Bare Git Repository
        ├── metadata/       # JSON-Dateien mit GitHub-Daten
        ├── snapshots/      # Point-in-time Backups
        └── status.json     # Letzter Backup-Status
```

## Logs

Logs werden in `logs/backup.log` gespeichert mit automatischer Rotation bei 100MB.

## Erweiterte Features

### Webhook-Signatur-Verifizierung
```bash
# Test der Signatur-Verifizierung
./ghbackup verify-webhook --body "test" --signature "sha256=..." --secret "secret"
```

### Snapshots
Automatische Snapshots werden erstellt bei:
- force-push Events
- branch-delete Events  
- tag-delete Events

Alte Snapshots werden nach 30 Tagen (konfigurierbar) automatisch gelöscht.

## Troubleshooting

### SSH-Authentifizierung fehlgeschlagen
```bash
# SSH-Key zu GitHub hinzufügen
ssh-keygen -t ed25519 -C "your_email@example.com"
# Füge den Public Key zu GitHub hinzu: https://github.com/settings/keys
```

### GitHub CLI nicht authentifiziert
```bash
gh auth login
# Folge den Anweisungen
```

### Rate Limiting
Das Tool respektiert automatisch GitHub's Rate Limits und wartet bei Bedarf.

## Entwicklung

### Tests ausführen
```bash
# Validierungstests
./ghbackup backup "invalid;name" repo  # Sollte fehlschlagen
./ghbackup backup account "../../../etc/passwd"  # Sollte fehlschlagen

# Normale Tests
./ghbackup backup YourAccount YourRepo
./ghbackup status
```

### Code-Stil
- Python 3.6+ kompatibel
- Type Hints verwenden
- Umfassende Fehlerbehandlung
- Sicherheit first: Validierung aller Inputs

## Lizenz

MIT License - siehe LICENSE Datei

## Beiträge

Contributions sind willkommen! Bitte erstelle einen Pull Request mit:
- Detaillierter Beschreibung der Änderungen
- Tests für neue Features
- Dokumentation-Updates

## Support

Bei Problemen oder Fragen:
- Issue erstellen auf GitHub
- Logs prüfen in `logs/backup.log`
- Dokumentation konsultieren

## Changelog

### v2.0.0 - Produktionsreife Version
- Umfassende Sicherheitsverbesserungen
- Eingabevalidierung für alle User-Inputs
- Command Injection Schutz
- Path Traversal Schutz
- Webhook-Signatur-Verifizierung
- Transactional Safety mit atomaren Operationen
- Verbesserte Fehlerbehandlung
- Timeout und Retry-Logik
- Sichere Token-Handhabung

### v1.0.0 - Initial Release
- Basis-Backup-Funktionalität
- Multi-Account Support
- SSH und Token Authentifizierung