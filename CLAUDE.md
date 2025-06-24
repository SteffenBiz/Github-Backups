# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a GitHub backup system written in Python that creates comprehensive backups of GitHub repositories, including both code and metadata (issues, PRs, releases). It supports multiple GitHub accounts and uses SSH authentication or GitHub CLI for secure access.

## Key Commands

### Running the backup system
```bash
# Backup single repository
./ghbackup backup <account> <repository>

# Backup all repositories in an account
./ghbackup backup <account> --all

# Backup all configured accounts
./ghbackup backup-all

# Show backup status
./ghbackup status

# Restore a repository
./ghbackup restore <account> <repository> <target-path>

# Event-driven backup (used by webhooks)
./ghbackup backup <account> <repository> --event <event-type>
```

### Development setup
```bash
# Create virtual environment
python3 -m venv venv

# Install dependencies
./venv/bin/pip install -r requirements.txt

# Check SSH authentication
ssh -T git@github.com

# Check GitHub CLI authentication
gh auth status
```

## Architecture

### Core Components

1. **ghbackup.py** - Main application implementing the GitHubBackup class
   - Handles all backup operations (clone, fetch, metadata)
   - Manages snapshots for critical events
   - Provides restoration functionality
   - Uses `gh` CLI or GitHub API for metadata

2. **ghbackup** - Shell wrapper that ensures Python virtual environment is active

3. **webhook-backup.sh** - Handles webhook events and triggers appropriate backups

### Key Classes and Methods

- `GitHubBackup` class in ghbackup.py:
  - `backup_repository()` - Main backup logic
  - `backup_metadata()` - Fetches GitHub API data
  - `create_snapshot()` - Creates point-in-time backups
  - `restore_repository()` - Restoration functionality
  - `cleanup_old_snapshots()` - Automatic snapshot management

### Configuration

- **config.yaml** - Main configuration (copy from config.yaml.example)
  - Contains account names and optional settings
  - SSH authentication recommended (no tokens needed)
  - Snapshot retention period (default: 30 days)

### Backup Structure
```
backups/
└── AccountName/
    └── Repository-Name/
        ├── repo.git/       # Bare Git repository
        ├── metadata/       # GitHub API data (JSON)
        ├── snapshots/      # Point-in-time backups
        └── status.json     # Last backup status
```

## Important Implementation Details

1. **Authentication**: Uses SSH keys or `gh` CLI - never stores tokens in code
2. **Error Handling**: Continues with other repos if one fails; comprehensive logging
3. **Snapshots**: Automatically created on force-push, branch-delete, tag-delete events
4. **Logging**: Automatic rotation at 100MB; thread-safe with file locking
5. **Incremental**: Only fetches new changes; efficient for large repositories

## Security Implementation

1. **Input Validation**: All user inputs validated with regex whitelists
2. **Command Injection Protection**: Uses shlex for safe command construction
3. **Path Traversal Protection**: Validates all paths stay within backup directory
4. **Webhook Security**: HMAC-SHA256 signature verification
5. **Atomic Operations**: Transactional safety with temp directories and rollback
6. **Timeouts**: All external operations have timeouts (Git: 300s, API: 30s)
7. **Retry Logic**: Decorator-based retry with exponential backoff

## Common Development Tasks

- When modifying backup logic, test with a small repository first
- Test security: `./ghbackup backup "test;rm -rf /" repo` (should fail)
- Check logs in `logs/backup.log` for debugging
- The system uses bare Git repositories for space efficiency
- Metadata is refreshed on every backup run
- Webhook events require signature verification if secret is configured
- Always validate inputs before processing