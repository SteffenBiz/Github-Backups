#!/usr/bin/env python3
"""
GitHub Backup Tool - Sichert GitHub-Repositories inkl. Metadaten
Produktionsreife Version mit umfassenden Sicherheitsverbesserungen
"""

import argparse
import os
import sys
import json
import yaml
import subprocess
import shutil
import shlex
import re
import threading
import hashlib
import hmac
from datetime import datetime
from pathlib import Path
import requests
from typing import Dict, List, Optional, Tuple
import time
import tempfile
import fcntl
from functools import wraps

# Konstanten
DEFAULT_TIMEOUT = 300  # 5 Minuten für Git-Operationen
API_TIMEOUT = 30  # 30 Sekunden für API-Calls
MAX_RETRIES = 3
RETRY_BACKOFF = 2
LOG_MAX_SIZE_MB = 100
RATE_LIMIT_THRESHOLD = 10
RATE_LIMIT_WAIT = 60

# Regex für Validierung
ACCOUNT_NAME_REGEX = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$')
REPO_NAME_REGEX = re.compile(r'^[a-zA-Z0-9._-]+$')
EVENT_TYPE_REGEX = re.compile(r'^[a-zA-Z0-9-]+$')

class ValidationError(Exception):
    """Raised when input validation fails"""
    pass

class BackupError(Exception):
    """Raised when backup operations fail"""
    pass

def retry_on_failure(max_attempts=MAX_RETRIES, backoff_factor=RETRY_BACKOFF):
    """Decorator für Retry-Logik bei Netzwerk-Operationen"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, subprocess.TimeoutExpired) as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = backoff_factor ** attempt
                        time.sleep(wait_time)
                    else:
                        raise
            raise last_exception
        return wrapper
    return decorator

class GitHubBackup:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self.load_config(config_path)
        self.backup_dir = Path("backups")
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)
        
        # Initialize logging with thread lock
        self.log_file = self.log_dir / "backup.log"
        self._log_lock = threading.Lock()
        self.check_log_rotation()
        
    def load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file with validation"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
            
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in config file: {e}")
            
        # Validate configuration structure
        if not isinstance(config, dict):
            raise ValueError("Config must be a dictionary")
        
        if 'accounts' not in config or not isinstance(config['accounts'], list):
            raise ValueError("Config must contain 'accounts' list")
            
        # Replace environment variables in tokens (optional for API access)
        for account in config.get('accounts', []):
            if not isinstance(account, dict) or 'name' not in account:
                raise ValueError("Each account must have a 'name' field")
                
            # Validate account name
            if not self._validate_account_name(account['name']):
                raise ValueError(f"Invalid account name: {account['name']}")
                
            token = account.get('token', '')
            if token and token.startswith('${') and token.endswith('}'):
                env_var = token[2:-1]
                account['token'] = os.environ.get(env_var, '')
                    
        return config
    
    def _validate_account_name(self, name: str) -> bool:
        """Validate GitHub account name"""
        return bool(ACCOUNT_NAME_REGEX.match(name) and len(name) <= 39)
    
    def _validate_repo_name(self, name: str) -> bool:
        """Validate repository name"""
        return bool(REPO_NAME_REGEX.match(name) and len(name) <= 100)
    
    def _validate_event_type(self, event: str) -> bool:
        """Validate event type"""
        return bool(EVENT_TYPE_REGEX.match(event) and len(event) <= 50)
    
    def _safe_path_join(self, base_dir: Path, *paths: str) -> Path:
        """Safely join paths preventing directory traversal"""
        base = base_dir.resolve()
        # Validate each path component
        for path in paths:
            if '..' in path or path.startswith('/') or path.startswith('\\'):
                raise ValidationError(f"Invalid path component: {path}")
        
        target = base.joinpath(*paths).resolve()
        
        # Ensure target is within base directory
        try:
            target.relative_to(base)
        except ValueError:
            raise ValidationError("Path traversal attempt detected")
            
        return target
        
    def log(self, message: str, level: str = "INFO"):
        """Thread-safe logging with rotation and fallback"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"{timestamp} {level} {message}\n"
        
        try:
            with self._log_lock:
                # Use file locking to prevent race conditions
                with open(self.log_file, 'a') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    try:
                        f.write(log_entry)
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except IOError as e:
            # Fallback to stderr
            sys.stderr.write(f"Logging failed: {e}\n{log_entry}")
            
        # Also print to console
        print(f"[{level}] {message}")
        
    def check_log_rotation(self):
        """Rotate log file if it exceeds max size with locking"""
        max_size = self.config.get('settings', {}).get('log_max_size_mb', LOG_MAX_SIZE_MB) * 1024 * 1024
        
        try:
            with self._log_lock:
                if self.log_file.exists() and self.log_file.stat().st_size > max_size:
                    old_log = self.log_dir / "backup.log.old"
                    # Atomic rotation
                    temp_name = self.log_dir / f"backup.log.{os.getpid()}"
                    self.log_file.rename(temp_name)
                    if old_log.exists():
                        old_log.unlink()
                    temp_name.rename(old_log)
        except Exception as e:
            sys.stderr.write(f"Log rotation failed: {e}\n")
            
    def get_github_api_headers(self, token: str) -> dict:
        """Get headers for GitHub API requests"""
        if token:
            return {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json'
            }
        return {'Accept': 'application/vnd.github.v3+json'}
        
    def run_git_command(self, cmd: List[str], cwd: Optional[Path] = None, timeout: int = DEFAULT_TIMEOUT) -> Tuple[bool, str]:
        """Run a git command safely with timeout"""
        # Ensure all arguments are properly quoted
        safe_cmd = [shlex.quote(str(arg)) if i > 0 else str(arg) for i, arg in enumerate(cmd)]
        
        try:
            result = subprocess.run(
                cmd,  # Use original cmd, not quoted version for subprocess
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
                timeout=timeout
            )
            return True, result.stdout
        except subprocess.CalledProcessError as e:
            return False, e.stderr
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
            
    def backup_repository_atomic(self, account: str, repo_name: str, token: str, event: Optional[str] = None) -> bool:
        """Atomic backup with rollback on failure"""
        # Validate inputs
        if not self._validate_account_name(account):
            raise ValidationError(f"Invalid account name: {account}")
        if not self._validate_repo_name(repo_name):
            raise ValidationError(f"Invalid repository name: {repo_name}")
        if event and not self._validate_event_type(event):
            raise ValidationError(f"Invalid event type: {event}")
            
        account_dir = self._safe_path_join(self.backup_dir, account)
        repo_dir = self._safe_path_join(account_dir, repo_name)
        temp_dir = None
        
        try:
            # Create temporary directory for atomic operation
            temp_dir = Path(tempfile.mkdtemp(dir=account_dir, prefix=f".{repo_name}_tmp_"))
            
            # Perform backup to temporary directory
            success = self._do_backup(temp_dir, account, repo_name, token, event)
            
            if success:
                # Atomic replace
                backup_dir = None
                if repo_dir.exists():
                    # Create backup of existing
                    backup_dir = repo_dir.with_suffix('.bak')
                    if backup_dir.exists():
                        shutil.rmtree(backup_dir)
                    repo_dir.rename(backup_dir)
                
                try:
                    # Move temp to final location
                    temp_dir.rename(repo_dir)
                    
                    # Remove backup on success
                    if backup_dir and backup_dir.exists():
                        shutil.rmtree(backup_dir)
                        
                except Exception:
                    # Rollback on failure
                    if backup_dir and backup_dir.exists():
                        if repo_dir.exists():
                            shutil.rmtree(repo_dir)
                        backup_dir.rename(repo_dir)
                    raise
                    
            return success
            
        except Exception as e:
            self.log(f"Backup failed for {account}/{repo_name}: {e}", "ERROR")
            return False
        finally:
            # Cleanup temporary directory
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
                    
    def _do_backup(self, repo_dir: Path, account: str, repo_name: str, token: str, event: Optional[str] = None) -> bool:
        """Perform actual backup operations"""
        self.log(f"START backup {account}/{repo_name}")
        
        # Create directory structure
        git_dir = repo_dir / "repo.git"
        metadata_dir = repo_dir / "metadata"
        snapshots_dir = repo_dir / "snapshots"
        
        git_dir.mkdir(exist_ok=True)
        metadata_dir.mkdir(exist_ok=True)
        snapshots_dir.mkdir(exist_ok=True)
        
        # Check if snapshot is needed for critical events
        if event in ['force-push', 'branch-delete', 'tag-delete']:
            # Note: snapshots are created from the main repo_dir, not temp
            parent_repo_dir = self._safe_path_join(self.backup_dir, account, repo_name)
            if parent_repo_dir.exists():
                self.create_snapshot(parent_repo_dir, event)
        
        # Backup git repository - check if SSH should be used
        use_ssh = False
        for acc in self.config.get('accounts', []):
            if acc['name'] == account and acc.get('use_ssh', False):
                use_ssh = True
                break
                
        if use_ssh:
            repo_url = f"git@github.com:{account}/{repo_name}.git"
        else:
            # Use git credential helper instead of embedding token in URL
            repo_url = f"https://github.com/{account}/{repo_name}.git"
        
        # Check if this is an update or initial clone
        existing_git_dir = self._safe_path_join(self.backup_dir, account, repo_name, "repo.git")
        
        if existing_git_dir.exists() and (existing_git_dir / "HEAD").exists():
            # Copy existing repo for update
            self.log(f"Updating existing backup for {account}/{repo_name}")
            shutil.copytree(existing_git_dir, git_dir, dirs_exist_ok=True)
            
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
            
            # Set up credentials if token provided
            env = os.environ.copy()
            if token and not use_ssh:
                # Use credential helper for secure token handling
                helper_script = self._create_credential_helper(token)
                env['GIT_ASKPASS'] = str(helper_script)
                
            try:
                success, output = self.run_git_command(
                    ['git', 'clone', '--mirror', repo_url, str(git_dir)],
                    timeout=DEFAULT_TIMEOUT * 2  # Double timeout for initial clone
                )
            finally:
                # Clean up credential helper
                if token and not use_ssh and 'GIT_ASKPASS' in env:
                    try:
                        Path(env['GIT_ASKPASS']).unlink()
                    except:
                        pass
                        
            if not success:
                self.log(f"ERROR {account}/{repo_name} - Failed to clone: {output}", "ERROR")
                return False
                
        # Get repository size
        try:
            size_result = subprocess.run(
                ['du', '-sh', str(git_dir)],
                capture_output=True,
                text=True,
                timeout=30
            )
            size = size_result.stdout.split()[0] if size_result.returncode == 0 else "unknown"
        except Exception:
            size = "unknown"
        
        # Backup metadata
        self.backup_metadata(account, repo_name, token, metadata_dir)
        
        # Update status
        status_file = repo_dir / "status.json"
        status = {
            'last_backup': datetime.now().isoformat(),
            'size': size,
            'event': event or 'manual'
        }
        
        try:
            with open(status_file, 'w') as f:
                json.dump(status, f, indent=2)
        except IOError as e:
            self.log(f"Failed to write status file: {e}", "WARNING")
            
        self.log(f"SUCCESS {account}/{repo_name} ({size})")
        return True
        
    def _create_credential_helper(self, token: str) -> Path:
        """Create a temporary credential helper script"""
        helper = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.sh')
        helper.write(f"""#!/bin/bash
echo "username=token"
echo "password={token}"
""")
        helper.close()
        os.chmod(helper.name, 0o700)
        return Path(helper.name)
        
    def backup_repository(self, account: str, repo_name: str, token: str, event: Optional[str] = None) -> bool:
        """Public interface for atomic backup"""
        try:
            return self.backup_repository_atomic(account, repo_name, token, event)
        except ValidationError as e:
            self.log(f"Validation error: {e}", "ERROR")
            return False
        except Exception as e:
            self.log(f"Unexpected error during backup: {e}", "ERROR")
            return False
            
    @retry_on_failure()
    def backup_metadata(self, account: str, repo_name: str, token: str, metadata_dir: Path):
        """Backup repository metadata using gh CLI or API with retry logic"""
        if not token:
            # Use gh CLI when no token is provided
            self.backup_metadata_with_gh(account, repo_name, metadata_dir)
        else:
            # Use API with token
            headers = self.get_github_api_headers(token)
            base_url = f"https://api.github.com/repos/{account}/{repo_name}"
            
            # Repository info
            try:
                resp = requests.get(base_url, headers=headers, timeout=API_TIMEOUT)
                resp.raise_for_status()
                with open(metadata_dir / "repository.json", 'w') as f:
                    json.dump(resp.json(), f, indent=2)
            except requests.RequestException as e:
                self.log(f"Failed to backup repository info: {e}", "ERROR")
                raise
                
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
        
        # Define metadata operations
        operations = [
            {
                'name': 'repository',
                'cmd': ['gh', 'api', f'repos/{repo}'],
                'file': 'repository.json'
            },
            {
                'name': 'issues',
                'cmd': ['gh', 'issue', 'list', '--repo', repo, '--state', 'all', '--json', 
                        'number,title,body,state,author,assignees,labels,createdAt,updatedAt,comments'],
                'file': 'issues.json'
            },
            {
                'name': 'pulls',
                'cmd': ['gh', 'pr', 'list', '--repo', repo, '--state', 'all', '--json',
                        'number,title,body,state,author,assignees,labels,createdAt,updatedAt,reviews,comments'],
                'file': 'pulls.json'
            },
            {
                'name': 'releases',
                'cmd': ['gh', 'release', 'list', '--repo', repo, '--json',
                        'tagName,name,body,isDraft,isPrerelease,createdAt,publishedAt,assets'],
                'file': 'releases.json',
                'allow_empty': True
            }
        ]
        
        for op in operations:
            try:
                result = subprocess.run(
                    op['cmd'],
                    capture_output=True,
                    text=True,
                    timeout=API_TIMEOUT
                )
                
                if result.returncode == 0:
                    data = json.loads(result.stdout) if result.stdout else []
                elif op.get('allow_empty', False):
                    data = []
                else:
                    self.log(f"Failed to backup {op['name']} with gh: {result.stderr}", "ERROR")
                    continue
                    
                with open(metadata_dir / op['file'], 'w') as f:
                    json.dump(data, f, indent=2)
                    
            except subprocess.TimeoutExpired:
                self.log(f"Timeout while backing up {op['name']} with gh", "ERROR")
            except Exception as e:
                self.log(f"Failed to backup {op['name']} with gh: {e}", "ERROR")
        
    @retry_on_failure()
    def backup_paginated_data(self, url: str, headers: dict, output_file: Path):
        """Backup paginated data from GitHub API with retry"""
        all_data = []
        page = 1
        
        while True:
            try:
                resp = requests.get(
                    f"{url}&page={page}&per_page=100", 
                    headers=headers,
                    timeout=API_TIMEOUT
                )
                resp.raise_for_status()
                    
                data = resp.json()
                if not data:
                    break
                    
                all_data.extend(data)
                page += 1
                
                # Respect rate limits
                if 'X-RateLimit-Remaining' in resp.headers:
                    remaining = int(resp.headers['X-RateLimit-Remaining'])
                    if remaining < RATE_LIMIT_THRESHOLD:
                        self.log("Approaching rate limit, waiting...", "WARNING")
                        time.sleep(RATE_LIMIT_WAIT)
                        
            except requests.RequestException as e:
                self.log(f"Failed to fetch {url}: {e}", "ERROR")
                if page == 1:
                    raise  # Re-raise if we couldn't get even the first page
                break  # Otherwise just stop pagination
                
        if all_data:
            try:
                with open(output_file, 'w') as f:
                    json.dump(all_data, f, indent=2)
            except IOError as e:
                self.log(f"Failed to write {output_file}: {e}", "ERROR")
                
    def create_snapshot(self, repo_dir: Path, event: str):
        """Create a snapshot of the repository"""
        snapshot_name = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_{event}"
        snapshot_dir = repo_dir / "snapshots" / snapshot_name
        
        self.log(f"SNAPSHOT {repo_dir.name} before {event}")
        
        try:
            # Create snapshot directory
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            
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
            
        except Exception as e:
            self.log(f"Failed to create snapshot: {e}", "ERROR")
            # Clean up partial snapshot
            if snapshot_dir.exists():
                try:
                    shutil.rmtree(snapshot_dir)
                except:
                    pass
        
    def clean_old_snapshots(self, snapshots_dir: Path):
        """Remove snapshots older than configured days"""
        keep_days = self.config.get('settings', {}).get('keep_snapshots_days', 30)
        cutoff = datetime.now().timestamp() - (keep_days * 24 * 60 * 60)
        
        try:
            for snapshot in snapshots_dir.iterdir():
                if snapshot.is_dir() and snapshot.stat().st_mtime < cutoff:
                    shutil.rmtree(snapshot)
                    self.log(f"Removed old snapshot: {snapshot.name}")
        except Exception as e:
            self.log(f"Error cleaning snapshots: {e}", "WARNING")
                
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
                    check=True,
                    timeout=API_TIMEOUT
                )
                if result.returncode == 0:
                    repos = json.loads(result.stdout)
                    for repo in repos:
                        if self._validate_repo_name(repo['name']):
                            self.backup_repository(account_name, repo['name'], token)
                        else:
                            self.log(f"Skipping invalid repo name: {repo['name']}", "WARNING")
                else:
                    self.log(f"Failed to list repositories with gh", "ERROR")
            except subprocess.TimeoutExpired:
                self.log(f"Timeout listing repositories for {account_name}", "ERROR")
            except Exception as e:
                self.log(f"Failed to backup account {account_name} with gh: {e}", "ERROR")
        else:
            # Use API with token
            self._backup_account_with_api(account_name, token)
            
    @retry_on_failure()
    def _backup_account_with_api(self, account_name: str, token: str):
        """Backup account using GitHub API"""
        headers = self.get_github_api_headers(token)
        repos_url = f"https://api.github.com/users/{account_name}/repos?type=all&per_page=100"
        
        try:
            resp = requests.get(repos_url, headers=headers, timeout=API_TIMEOUT)
            resp.raise_for_status()
                
            repos = resp.json()
            
            for repo in repos:
                if repo['owner']['login'] == account_name:
                    if self._validate_repo_name(repo['name']):
                        self.backup_repository(account_name, repo['name'], token)
                    else:
                        self.log(f"Skipping invalid repo name: {repo['name']}", "WARNING")
                        
        except requests.RequestException as e:
            self.log(f"Failed to backup account {account_name}: {e}", "ERROR")
            raise
            
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
                if not repo_dir.is_dir() or repo_dir.name.startswith('.'):
                    continue
                    
                status_file = repo_dir / "status.json"
                if status_file.exists():
                    try:
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
                    except Exception as e:
                        print(f"├── {repo_dir.name:<30} ✗ Error reading status: {e}")
                else:
                    print(f"├── {repo_dir.name:<30} ✗ No backup found")
                    
            print()
            
    def restore_repository(self, account: str, repo_name: str, target_path: str):
        """Restore a repository to target path"""
        # Validate inputs
        if not self._validate_account_name(account):
            self.log(f"Invalid account name: {account}", "ERROR")
            return False
        if not self._validate_repo_name(repo_name):
            self.log(f"Invalid repository name: {repo_name}", "ERROR")
            return False
            
        repo_dir = self._safe_path_join(self.backup_dir, account, repo_name)
        git_dir = repo_dir / "repo.git"
        
        if not git_dir.exists():
            self.log(f"No backup found for {account}/{repo_name}", "ERROR")
            return False
            
        target = Path(target_path).resolve()
        
        # Prevent restore to system directories
        system_dirs = ['/etc', '/usr', '/bin', '/sbin', '/var', '/tmp', '/dev', '/proc', '/sys']
        for sys_dir in system_dirs:
            if str(target).startswith(sys_dir):
                self.log(f"Cannot restore to system directory: {target_path}", "ERROR")
                return False
                
        if target.exists():
            self.log(f"Target path already exists: {target_path}", "ERROR")
            return False
            
        self.log(f"Restoring {account}/{repo_name} to {target_path}")
        
        try:
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
            
        except Exception as e:
            self.log(f"Restore failed: {e}", "ERROR")
            # Clean up partial restore
            if target.exists():
                try:
                    shutil.rmtree(target)
                except:
                    pass
            return False

    def verify_webhook_signature(self, body: bytes, signature: str, secret: str) -> bool:
        """Verify GitHub webhook signature"""
        if not signature or not secret:
            return False
            
        # GitHub sends signature as 'sha256=...'
        if not signature.startswith('sha256='):
            return False
            
        expected = hmac.new(
            secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()
        
        provided = signature[7:]  # Remove 'sha256=' prefix
        
        # Use constant-time comparison
        return hmac.compare_digest(expected, provided)


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
    
    # Webhook verify command (for testing)
    webhook_parser = subparsers.add_parser('verify-webhook', help='Verify webhook signature')
    webhook_parser.add_argument('--body', required=True, help='Request body')
    webhook_parser.add_argument('--signature', required=True, help='GitHub signature header')
    webhook_parser.add_argument('--secret', required=True, help='Webhook secret')
    
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
                    
                success = backup.backup_repository(args.account, args.repo, token, args.event)
                sys.exit(0 if success else 1)
            else:
                backup.backup_account(args.account)
                
        elif args.command == 'backup-all':
            backup.backup_all_accounts()
            
        elif args.command == 'status':
            backup.show_status()
            
        elif args.command == 'restore':
            success = backup.restore_repository(args.account, args.repo, args.target)
            sys.exit(0 if success else 1)
            
        elif args.command == 'verify-webhook':
            # Test webhook signature verification
            valid = backup.verify_webhook_signature(
                args.body.encode('utf-8'),
                args.signature,
                args.secret
            )
            print(f"Signature valid: {valid}")
            sys.exit(0 if valid else 1)
            
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except ValidationError as e:
        print(f"Validation error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()