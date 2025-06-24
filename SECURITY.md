# Security Policy

## Reporting Security Vulnerabilities

If you discover a security vulnerability in this project, please report it responsibly:

1. **DO NOT** create a public issue
2. Send details to: security@steffenbiz.com
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will acknowledge receipt within 48 hours and provide updates on the fix.

## Security Features

### Input Validation
- All user inputs are validated using whitelist approach
- Account names: `^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$` (max 39 chars)
- Repository names: `^[a-zA-Z0-9._-]+$` (max 100 chars)
- Event types: `^[a-zA-Z0-9-]+$` (max 50 chars)

### Command Injection Protection
- No direct string concatenation in shell commands
- All arguments properly quoted using `shlex`
- Subprocess calls with explicit argument lists

### Path Traversal Protection
- Path validation prevents `..` and absolute paths
- All paths resolved and verified to be within backup directory
- System directory restoration blocked

### Authentication Security
- SSH authentication recommended (no tokens in code)
- GitHub CLI (`gh`) as secure alternative
- Token never embedded in Git URLs
- Credential helper for secure token handling

### Webhook Security
- HMAC-SHA256 signature verification
- Constant-time comparison for signatures
- Optional IP whitelisting for GitHub webhooks

### Operational Security
- Atomic backup operations with rollback
- Thread-safe logging with file locking
- Automatic log rotation
- Timeout protection for all external operations
- Retry logic with exponential backoff
- Rate limit respect

## Best Practices

### Configuration
```yaml
# Use environment variables for secrets
webhook:
  secret: ${WEBHOOK_SECRET}

# Use SSH instead of tokens
accounts:
  - name: YourAccount
    use_ssh: true
```

### Webhook Setup
1. Generate strong secret: `openssl rand -hex 32`
2. Set secret in GitHub webhook settings
3. Export as environment variable: `export WEBHOOK_SECRET=...`

### File Permissions
```bash
# Protect configuration
chmod 600 config.yaml

# Protect backups
chmod 700 backups/

# Protect logs
chmod 700 logs/
```

### Running in Production
1. Use a dedicated user account
2. Set up proper file permissions
3. Monitor logs regularly
4. Test restore procedures
5. Keep dependencies updated

## Security Checklist

- [ ] SSH keys configured and tested
- [ ] No tokens in configuration files
- [ ] Webhook secret configured
- [ ] File permissions set correctly
- [ ] Logs monitored for errors
- [ ] Backup integrity verified
- [ ] Restore tested regularly
- [ ] Dependencies up to date

## Known Limitations

1. **Log Masking**: While sensitive data is protected, ensure logs are secured
2. **Network Security**: Use VPN or secure network for backups
3. **Storage Encryption**: Consider encrypting backup directory at rest

## Updates and Patches

Security updates will be released as soon as possible after discovery.
Monitor the repository for updates and subscribe to security advisories.