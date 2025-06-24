# GitHub Backup System - Features

## Backup-Funktionen

### Git-Repository-Backup
- Vollständige Mirror-Kopie (alle Branches, Tags, Historie)
- Inkrementelle Updates (nur neue Commits)
- Bare Repository Format (platzsparend)

### Metadaten-Backup
- Issues mit allen Kommentaren
- Pull Requests mit Reviews
- Releases mit Assets-Informationen
- Repository-Einstellungen

### Snapshot-System
Automatische Snapshots bei kritischen Events:
- `force-push`: Sichert Zustand vor Überschreibung
- `branch-delete`: Sichert gelöschte Branches
- `tag-delete`: Sichert gelöschte Tags

### Multi-Account-Support
- Beliebig viele GitHub-Accounts
- Zentrale Konfiguration
- Account-spezifische Einstellungen

## Technische Details

### Authentifizierung
- SSH für Git-Operationen (kein Token im Code)
- GitHub CLI (`gh`) für API-Zugriffe
- Keine Passwörter oder Tokens in Konfiguration nötig

### Fehlerbehandlung
- Resilient gegen Netzwerkfehler
- Fortsetzung bei einzelnen fehlgeschlagenen Repos
- Detailliertes Logging aller Operationen

### Performance
- Parallelisierung möglich (mehrere Repos gleichzeitig)
- Nur geänderte Daten werden übertragen
- Effiziente Speichernutzung durch Git-Objektmodell

### Automatisierung
- Webhook-Integration für Event-basierte Backups
- Cron-kompatibel für regelmäßige Backups
- Exit-Codes für Skript-Integration