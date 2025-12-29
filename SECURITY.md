# Security Checklist

## ✅ Verified - Safe to Commit

- [x] `.env` file is in `.gitignore` - contains actual credentials
- [x] `oauth_tokens.txt` is in `.gitignore` - contains session tokens
- [x] `activities_cache.json` is in `.gitignore` - may contain personal data
- [x] `.venv/` is in `.gitignore` - virtual environment
- [x] `.vscode/` is in `.gitignore` - personal IDE settings
- [x] Pre-commit hook includes `detect-private-key`
- [x] All credentials loaded from environment variables only
- [x] No hardcoded tokens, passwords, or API keys in code
- [x] `.env.example` contains only placeholder values
- [x] README contains only example/placeholder values

## Environment Variables (Not in Repo)

The following are loaded from `.env` and **never** committed:

- `GARMIN_SESSION` - OAuth session token for Garmin Connect

## Files to Never Commit

- `.env` - actual credentials
- `oauth_tokens.txt` - session token backup
- `activities_cache.json` - personal activity data
- `.venv/` - virtual environment
- `node_modules/` - npm dependencies

## Safe to Commit

- `.env.example` - template with placeholders only
- All Python code - uses env vars only
- All configuration files
- Documentation
