# Setup-Anleitung

## Voraussetzungen prüfen

### 1. SSH-Verbindung zu GitHub
```bash
ssh -T git@github.com
```
Sollte antworten: "Hi username! You've successfully authenticated..."

### 2. GitHub CLI installiert
```bash
gh --version
```
Falls nicht installiert: https://cli.github.com/

### 3. GitHub CLI authentifiziert
```bash
gh auth status
```
Falls nicht authentifiziert:
```bash
gh auth login
```

## Installation

1. **Repository klonen**
```bash
git clone <dieses-repo>
cd github-backups
```

2. **Virtual Environment einrichten**
```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

3. **Konfiguration erstellen**
```bash
cp config.yaml.example config.yaml
```

4. **config.yaml anpassen**
```yaml
accounts:
  - name: DeinGitHubUsername
    use_ssh: true
```

## Erste Schritte

```bash
# Test - Status anzeigen
./ghbackup status

# Erstes Backup eines Repos
./ghbackup backup DeinUsername DeinRepo

# Alle Repos backuppen
./ghbackup backup DeinUsername --all
```

## Automatisierung

Für regelmäßige Backups via Cron:
```bash
# Crontab editieren
crontab -e

# Täglich um 2 Uhr nachts alle Repos backuppen
0 2 * * * cd /path/to/github-backups && ./ghbackup backup-all
```

## Troubleshooting

- **"gh: command not found"**: GitHub CLI installieren
- **"Permission denied (publickey)"**: SSH-Key nicht konfiguriert
- **Keine Metadaten gesichert**: `gh auth status` prüfen