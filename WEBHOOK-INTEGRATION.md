# Webhook Integration Guide

## Übersicht

Das GitHub Backup System ist so konzipiert, dass es mit einem externen Webhook-Server zusammenarbeitet. Das Backup-System selbst hat **keine eigene Webhook-Funktionalität** - es wird vom Webhook-Server aufgerufen.

## Architektur

```
┌─────────────┐     Push Event      ┌──────────────────┐
│   GitHub    │ ─────────────────>  │  Webhook-Server  │
│ Repository  │                     │  (pixel-hotel)   │
└─────────────┘                     └────────┬─────────┘
                                             │
                                             │ Führt Befehl aus
                                             ↓
                                    ┌────────────────────┐
                                    │ webhook-backup.sh  │
                                    └────────┬───────────┘
                                             │
                                             │ Ruft auf
                                             ↓
                                    ┌────────────────────┐
                                    │    ghbackup.py     │
                                    │  (Backup-System)   │
                                    └────────────────────┘
```

## Komponenten

### 1. Webhook-Server (Externes Projekt)
- **Repository**: [Github-Webhook](https://github.com/SteffenBiz/Github-Webhook)
- **Läuft auf**: pixel-hotel oder anderem Server
- **Aufgabe**: 
  - Empfängt GitHub Events
  - Verifiziert Signaturen
  - Führt konfigurierte Befehle aus

### 2. Backup-System (Dieses Projekt)
- **Repository**: Github-Backups
- **Läuft auf**: Demselben Server wie Webhook-Server
- **Aufgabe**:
  - Wird vom Webhook-Server aufgerufen
  - Erstellt Backups
  - Ist eine passive Komponente

## Konfiguration

### Webhook-Server Konfiguration
Die `webhook-config.json` gehört zum **Webhook-Server**, nicht zum Backup-System:

```json
{
  "repository_commands": {
    "SteffenBiz/Test-Repo": {
      "refs/heads/main": "/pfad/zu/webhook-backup.sh Test-Repo push"
    }
  }
}
```

### Backup-System Konfiguration
Das Backup-System benötigt nur die normale `config.yaml`:

```yaml
accounts:
  - name: SteffenBiz
    use_ssh: true

settings:
  keep_snapshots_days: 30
```

## Setup-Anleitung

### 1. Webhook-Server einrichten (falls noch nicht geschehen)
```bash
# Auf pixel-hotel
git clone https://github.com/SteffenBiz/Github-Webhook.git
cd Github-Webhook
# Folge der Anleitung im Webhook-Server Repository
```

### 2. Backup-System installieren
```bash
# Auf demselben Server
git clone https://github.com/SteffenBiz/Github-Backups.git
cd Github-Backups
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp config.yaml.example config.yaml
# Editiere config.yaml
```

### 3. Webhook-Server konfigurieren
Füge in die `webhook-config.json` des Webhook-Servers ein:

```json
"Dein-Account/Dein-Repo": {
  "refs/heads/main": "/absoluter/pfad/zu/Github-Backups/webhook-backup.sh Dein-Repo push"
}
```

### 4. GitHub Webhook einrichten
In deinem GitHub Repository:
1. Settings → Webhooks → Add webhook
2. Payload URL: `http://pixel-hotel:port/webhook`
3. Content type: `application/json`
4. Secret: Dein Webhook-Secret
5. Events: Push events (oder andere)

## Sicherheit

### Webhook-Signatur-Verifizierung
- **Primär**: Der Webhook-Server verifiziert die GitHub-Signatur
- **Optional**: Das Backup-System kann die Signatur nochmals prüfen, wenn der Webhook-Server sie weitergibt

### Eingabevalidierung
Das `webhook-backup.sh` Script validiert alle Eingaben:
- Repository-Namen
- Event-Typen
- Verhindert Command Injection
- Verhindert Path Traversal

## Verwendung

### Automatisch (via Webhook)
Sobald eingerichtet, läuft alles automatisch:
1. Du pushst zu GitHub
2. GitHub sendet Event an Webhook-Server
3. Webhook-Server ruft Backup-System auf
4. Backup wird erstellt

### Manuell (direkt)
Du kannst das Backup-System auch manuell aufrufen:
```bash
./ghbackup backup SteffenBiz Test-Repo
```

## Troubleshooting

### Webhook wird nicht ausgelöst
1. Prüfe GitHub Webhook Settings → Recent Deliveries
2. Prüfe Webhook-Server Logs
3. Stelle sicher, dass der Server erreichbar ist

### Backup schlägt fehl
1. Prüfe `logs/backup.log`
2. Teste manuellen Aufruf
3. Prüfe SSH-Authentifizierung

### Signatur-Fehler
1. Stelle sicher, dass das Secret übereinstimmt
2. Prüfe, ob der Webhook-Server die Signatur korrekt weitergibt

## Wichtige Hinweise

- Das Backup-System ist **passiv** und wartet auf Aufrufe
- Der Webhook-Server ist **aktiv** und empfängt Events
- Die `webhook-config.json` gehört zum Webhook-Server
- Die `config.yaml` gehört zum Backup-System
- Beide Systeme sollten auf demselben Server laufen