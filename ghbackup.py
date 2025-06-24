#!/usr/bin/env python3
"""
GitHub Backup Tool - Sichert GitHub-Repositories inkl. Metadaten
"""

import argparse
import os
import sys
import json
import yaml
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
import requests
from typing import Dict, List, Optional, Tuple
import time

class GitHubBackup:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self.load_config(config_path)
        self.backup_dir = Path("backups")
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)
        
        # Initialize logging
        self.log_file = self.log_dir / "backup.log"
        self.check_log_rotation()
        
    def load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
            
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            
        # Replace environment variables in tokens (optional for API access)
        for account in config.get('accounts', []):
            token = account.get('token', '')
            if token and token.startswith('${') and token.endswith('}'):
                env_var = token[2:-1]
                account['token'] = os.environ.get(env_var, '')
                    
        return config
        
    def log(self, message: str, level: str = "INFO"):
        """Simple logging with rotation"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"{timestamp} {level} {message}\n"
        
        with open(self.log_file, 'a') as f:
            f.write(log_entry)
            
        # Also print to console
        print(f"[{level}] {message}")
        
    def check_log_rotation(self):
        """Rotate log file if it exceeds max size"""
        max_size = self.config.get('settings', {}).get('log_max_size_mb', 100) * 1024 * 1024
        
        if self.log_file.exists() and self.log_file.stat().st_size > max_size:
            old_log = self.log_dir / "backup.log.old"
            if old_log.exists():
                old_log.unlink()
            self.log_file.rename(old_log)
            
    def get_github_api_headers(self, token: str) -> dict:
        """Get headers for GitHub API requests"""
        if token:
            return {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json'
            }
        return {'Accept': 'application/vnd.github.v3+json'}
        
    def run_git_command(self, cmd: List[str], cwd: Optional[Path] = None) -> Tuple[bool, str]:
        """Run a git command and return success status and output"""
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True
            )
            return True, result.stdout
        except subprocess.CalledProcessError as e:
            return False, e.stderr
            
    def backup_repository(self, account: str, repo_name: str, token: str, event: Optional[str] = None) -> bool:
        """Backup a single repository"""
        self.log(f"START backup {account}/{repo_name}")
        
        # Create backup directory structure
        account_dir = self.backup_dir / account
        repo_dir = account_dir / repo_name
        git_dir = repo_dir / "repo.git"
        metadata_dir = repo_dir / "metadata"
        snapshots_dir = repo_dir / "snapshots"
        
        account_dir.mkdir(exist_ok=True)
        repo_dir.mkdir(exist_ok=True)
        metadata_dir.mkdir(exist_ok=True)
        snapshots_dir.mkdir(exist_ok=True)
        
        # Check if snapshot is needed for critical events
        if event in ['force-push', 'branch-delete', 'tag-delete']:
            self.create_snapshot(repo_dir, event)
        
        # Backup git repository - check if SSH should be used
        use_ssh = False
        for acc in self.config.get('accounts', []):
            if acc['name'] == account and acc.get('use_ssh', False):
                use_ssh = True
                break
                
        if use_ssh:
            repo_url = f"git@github.com:{account}/{repo_name}.git"
        else:
            repo_url = f"https://{token}@github.com/{account}/{repo_name}.git"
        
        if git_dir.exists():
            # Update existing backup
            self.log(f"Updating existing backup for {account}/{repo_name}")
            success, output = self.run_git_command(
                ['git', 'fetch', '--all', '--prune'], 
                cwd=git_dir
            )
            if not success:
                self.log(f"ERROR {account}/{repo_name} - Failed to fetch: {output}", "ERROR")
                return False
        else:
            # Initial clone
            self.log(f"Creating initial backup for {account}/{repo_name}")
            success, output = self.run_git_command(
                ['git', 'clone', '--mirror', repo_url, str(git_dir)]
            )
            if not success:
                self.log(f"ERROR {account}/{repo_name} - Failed to clone: {output}", "ERROR")
                return False
                
        # Get repository size
        size_cmd = ['du', '-sh', str(git_dir)]
        size_result = subprocess.run(size_cmd, capture_output=True, text=True)
        size = size_result.stdout.split()[0] if size_result.returncode == 0 else "unknown"
        
        # Backup metadata
        self.backup_metadata(account, repo_name, token, metadata_dir)
        
        # Update status
        status_file = repo_dir / "status.json"
        status = {
            'last_backup': datetime.now().isoformat(),
            'size': size,
            'event': event or 'manual'
        }
        with open(status_file, 'w') as f:
            json.dump(status, f, indent=2)
            
        self.log(f"SUCCESS {account}/{repo_name} ({size})")
        return True
        
    def backup_metadata(self, account: str, repo_name: str, token: str, metadata_dir: Path):
        """Backup repository metadata using gh CLI or API"""
        if not token:
            # Use gh CLI when no token is provided
            self.backup_metadata_with_gh(account, repo_name, metadata_dir)
        else:
            # Use API with token
            headers = self.get_github_api_headers(token)
            base_url = f"https://api.github.com/repos/{account}/{repo_name}"
            
            # Repository info
            try:
                resp = requests.get(base_url, headers=headers)
                if resp.status_code == 200:
                    with open(metadata_dir / "repository.json", 'w') as f:
                        json.dump(resp.json(), f, indent=2)
            except Exception as e:
                self.log(f"Failed to backup repository info: {e}", "ERROR")
                
            # Issues
            self.backup_paginated_data(
                f"{base_url}/issues?state=all", 
                headers, 
                metadata_dir / "issues.json"
            )
            
            # Pull requests
            self.backup_paginated_data(
                f"{base_url}/pulls?state=all", 
                headers, 
                metadata_dir / "pulls.json"
            )
            
            # Releases
            self.backup_paginated_data(
                f"{base_url}/releases", 
                headers, 
                metadata_dir / "releases.json"
            )
            
    def backup_metadata_with_gh(self, account: str, repo_name: str, metadata_dir: Path):
        """Backup repository metadata using gh CLI"""
        repo = f"{account}/{repo_name}"
        
        # Repository info
        try:
            result = subprocess.run(
                ['gh', 'api', f'repos/{repo}'],
                capture_output=True,
                text=True,
                check=True
            )
            if result.returncode == 0:
                with open(metadata_dir / "repository.json", 'w') as f:
                    json.dump(json.loads(result.stdout), f, indent=2)
        except Exception as e:
            self.log(f"Failed to backup repository info with gh: {e}", "ERROR")
            
        # Issues
        try:
            result = subprocess.run(
                ['gh', 'issue', 'list', '--repo', repo, '--state', 'all', '--json', 
                 'number,title,body,state,author,assignees,labels,createdAt,updatedAt,comments'],
                capture_output=True,
                text=True,
                check=True
            )
            if result.returncode == 0:
                with open(metadata_dir / "issues.json", 'w') as f:
                    json.dump(json.loads(result.stdout), f, indent=2)
        except Exception as e:
            self.log(f"Failed to backup issues with gh: {e}", "ERROR")
            
        # Pull requests
        try:
            result = subprocess.run(
                ['gh', 'pr', 'list', '--repo', repo, '--state', 'all', '--json',
                 'number,title,body,state,author,assignees,labels,createdAt,updatedAt,reviews,comments'],
                capture_output=True,
                text=True,
                check=True
            )
            if result.returncode == 0:
                with open(metadata_dir / "pulls.json", 'w') as f:
                    json.dump(json.loads(result.stdout), f, indent=2)
        except Exception as e:
            self.log(f"Failed to backup PRs with gh: {e}", "ERROR")
            
        # Releases
        try:
            result = subprocess.run(
                ['gh', 'release', 'list', '--repo', repo, '--json',
                 'tagName,name,body,isDraft,isPrerelease,createdAt,publishedAt,assets'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                with open(metadata_dir / "releases.json", 'w') as f:
                    json.dump(json.loads(result.stdout), f, indent=2)
            else:
                # No releases found is not an error
                with open(metadata_dir / "releases.json", 'w') as f:
                    json.dump([], f, indent=2)
        except Exception as e:
            self.log(f"Failed to backup releases with gh: {e}", "ERROR")
        
    def backup_paginated_data(self, url: str, headers: dict, output_file: Path):
        """Backup paginated data from GitHub API"""
        all_data = []
        page = 1
        
        while True:
            try:
                resp = requests.get(f"{url}&page={page}&per_page=100", headers=headers)
                if resp.status_code != 200:
                    break
                    
                data = resp.json()
                if not data:
                    break
                    
                all_data.extend(data)
                page += 1
                
                # Respect rate limits
                if 'X-RateLimit-Remaining' in resp.headers:
                    remaining = int(resp.headers['X-RateLimit-Remaining'])
                    if remaining < 10:
                        self.log("Approaching rate limit, waiting...", "WARNING")
                        time.sleep(60)
                        
            except Exception as e:
                self.log(f"Failed to fetch {url}: {e}", "ERROR")
                break
                
        if all_data:
            with open(output_file, 'w') as f:
                json.dump(all_data, f, indent=2)
                
    def create_snapshot(self, repo_dir: Path, event: str):
        """Create a snapshot of the repository"""
        snapshot_name = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_{event}"
        snapshot_dir = repo_dir / "snapshots" / snapshot_name
        
        self.log(f"SNAPSHOT {repo_dir.name} before {event}")
        
        # Copy current state
        if (repo_dir / "repo.git").exists():
            shutil.copytree(
                repo_dir / "repo.git",
                snapshot_dir / "repo.git",
                dirs_exist_ok=True
            )
            
        if (repo_dir / "metadata").exists():
            shutil.copytree(
                repo_dir / "metadata",
                snapshot_dir / "metadata",
                dirs_exist_ok=True
            )
            
        # Clean old snapshots
        self.clean_old_snapshots(repo_dir / "snapshots")
        
    def clean_old_snapshots(self, snapshots_dir: Path):
        """Remove snapshots older than configured days"""
        keep_days = self.config.get('settings', {}).get('keep_snapshots_days', 30)
        cutoff = datetime.now().timestamp() - (keep_days * 24 * 60 * 60)
        
        for snapshot in snapshots_dir.iterdir():
            if snapshot.is_dir() and snapshot.stat().st_mtime < cutoff:
                shutil.rmtree(snapshot)
                self.log(f"Removed old snapshot: {snapshot.name}")
                
    def backup_account(self, account_name: str):
        """Backup all repositories for an account"""
        account_config = None
        for acc in self.config.get('accounts', []):
            if acc['name'] == account_name:
                account_config = acc
                break
                
        if not account_config:
            self.log(f"Account {account_name} not found in config", "ERROR")
            return
            
        token = account_config.get('token', '')
        
        # Get all repositories using gh CLI if no token
        if not token:
            try:
                result = subprocess.run(
                    ['gh', 'repo', 'list', account_name, '--json', 'name', '--limit', '1000'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                if result.returncode == 0:
                    repos = json.loads(result.stdout)
                    for repo in repos:
                        self.backup_repository(account_name, repo['name'], token)
                else:
                    self.log(f"Failed to list repositories with gh", "ERROR")
            except Exception as e:
                self.log(f"Failed to backup account {account_name} with gh: {e}", "ERROR")
        else:
            # Use API with token
            headers = self.get_github_api_headers(token)
            repos_url = f"https://api.github.com/users/{account_name}/repos?type=all&per_page=100"
            
            try:
                resp = requests.get(repos_url, headers=headers)
                if resp.status_code != 200:
                    self.log(f"Failed to list repositories: {resp.status_code}", "ERROR")
                    return
                    
                repos = resp.json()
                
                for repo in repos:
                    if repo['owner']['login'] == account_name:
                        self.backup_repository(account_name, repo['name'], token)
                        
            except Exception as e:
                self.log(f"Failed to backup account {account_name}: {e}", "ERROR")
            
    def backup_all_accounts(self):
        """Backup all configured accounts"""
        for account in self.config.get('accounts', []):
            self.backup_account(account['name'])
            
    def show_status(self):
        """Show status of all backups"""
        print("\n=== GitHub Backup Status ===\n")
        
        for account_dir in sorted(self.backup_dir.iterdir()):
            if not account_dir.is_dir():
                continue
                
            print(f"ACCOUNT: {account_dir.name}")
            
            for repo_dir in sorted(account_dir.iterdir()):
                if not repo_dir.is_dir():
                    continue
                    
                status_file = repo_dir / "status.json"
                if status_file.exists():
                    with open(status_file, 'r') as f:
                        status = json.load(f)
                        
                    last_backup = datetime.fromisoformat(status['last_backup'])
                    age = datetime.now() - last_backup
                    
                    # Status symbol
                    if age.days == 0:
                        symbol = "✓"
                    elif age.days < 7:
                        symbol = "⚠"
                    else:
                        symbol = "✗"
                        
                    print(f"├── {repo_dir.name:<30} {symbol} {last_backup.strftime('%Y-%m-%d %H:%M')}  ({status['size']})")
                else:
                    print(f"├── {repo_dir.name:<30} ✗ No backup found")
                    
            print()
            
    def restore_repository(self, account: str, repo_name: str, target_path: str):
        """Restore a repository to target path"""
        repo_dir = self.backup_dir / account / repo_name
        git_dir = repo_dir / "repo.git"
        
        if not git_dir.exists():
            self.log(f"No backup found for {account}/{repo_name}", "ERROR")
            return False
            
        target = Path(target_path)
        if target.exists():
            self.log(f"Target path already exists: {target_path}", "ERROR")
            return False
            
        self.log(f"Restoring {account}/{repo_name} to {target_path}")
        
        # Clone from backup
        success, output = self.run_git_command(
            ['git', 'clone', str(git_dir), str(target)]
        )
        
        if not success:
            self.log(f"Failed to restore: {output}", "ERROR")
            return False
            
        # Copy metadata
        metadata_src = repo_dir / "metadata"
        metadata_dst = target / ".github-backup-metadata"
        if metadata_src.exists():
            shutil.copytree(metadata_src, metadata_dst)
            
        self.log(f"Successfully restored {account}/{repo_name}")
        print(f"\nMetadata saved to: {metadata_dst}")
        print("Note: Issues, PRs, and other metadata must be manually imported to GitHub")
        
        return True


def main():
    parser = argparse.ArgumentParser(description='GitHub Backup Tool')
    parser.add_argument('--config', default='config.yaml', help='Config file path')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Backup command
    backup_parser = subparsers.add_parser('backup', help='Backup repositories')
    backup_parser.add_argument('account', help='Account name')
    backup_parser.add_argument('repo', nargs='?', help='Repository name (optional)')
    backup_parser.add_argument('--all', action='store_true', help='Backup all repos in account')
    backup_parser.add_argument('--event', help='Event type (for webhook integration)')
    
    # Backup-all command
    subparsers.add_parser('backup-all', help='Backup all configured accounts')
    
    # Status command
    subparsers.add_parser('status', help='Show backup status')
    
    # Restore command
    restore_parser = subparsers.add_parser('restore', help='Restore a repository')
    restore_parser.add_argument('account', help='Account name')
    restore_parser.add_argument('repo', help='Repository name')
    restore_parser.add_argument('target', help='Target directory path')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
        
    try:
        backup = GitHubBackup(args.config)
        
        if args.command == 'backup':
            if args.repo and not args.all:
                # Find token for account
                token = None
                for acc in backup.config.get('accounts', []):
                    if acc['name'] == args.account:
                        token = acc.get('token', '')
                        break
                # Token is now optional - gh CLI will be used if not set
                    
                backup.backup_repository(args.account, args.repo, token, args.event)
            else:
                backup.backup_account(args.account)
                
        elif args.command == 'backup-all':
            backup.backup_all_accounts()
            
        elif args.command == 'status':
            backup.show_status()
            
        elif args.command == 'restore':
            backup.restore_repository(args.account, args.repo, args.target)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()