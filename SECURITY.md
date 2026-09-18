# RVB Vault security decisions

## Local secrets

Secret field values are stored only in `value_secret` after AES-256-GCM encryption. The random vault key is protected by Windows DPAPI for the signed-in Windows user. Secret values are omitted from `value_text` and the FTS5 search index.

## Authentication and locking

Windows Hello uses `Windows.Security.Credentials.UI.UserConsentVerifier`. Windows displays and evaluates the PIN, fingerprint, or face prompt; RVB Vault receives only the verification result. The app locks after 15 minutes by default and reacts to Windows session lock and suspend messages. Locking masks and removes decrypted entry widgets and clears RVB-owned sensitive clipboard content when it is still unchanged.

An optional master-password verifier is PBKDF2-HMAC-SHA256 with a random salt. It is a fallback gate, not encryption key material, and the password itself is never stored.

## Exports and backups

Safe JSON and collection exports keep secret-field metadata but set secret values to `null` and mark them redacted. Updating from a redacted export preserves an existing matching secret rather than blanking it.

Portable full backups use Scrypt (`N=32768`, `r=8`, `p=1`) to derive a key and AES-256-GCM for authenticated encryption. Local rolling backups use the DPAPI-protected vault key. SQLite snapshots and integrity validation are performed in memory; plaintext database snapshots are not written to temporary files.

## Files and diagnostics

Data is stored under the current user's `%LOCALAPPDATA%\RVB Vault` profile directory and inherits its Windows access controls. Crash logs contain exception diagnostics only; application code does not log entry or secret values.
