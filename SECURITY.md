# RVB Vault security decisions

## Local secrets

Secret field values are stored only in `value_secret` after AES-256-GCM encryption. The random vault key is protected by Windows DPAPI for the signed-in Windows user. Secret values are omitted from `value_text` and the FTS5 search index.

## Authentication and locking

Windows Hello desktop unlock is unavailable in this build. Microsoft documents `UserConsentVerifier.RequestVerificationAsync` as UWP-only for this use; using it in an unpackaged Qt desktop app did not produce a reliable window-owned prompt. RVB Vault fails closed by requiring a master password before first opening the vault and never handles a Windows PIN or biometric data. The app locks after 15 minutes by default and reacts to Windows session lock and suspend messages. Locking masks and removes decrypted entry widgets and clears RVB-owned sensitive clipboard content when it is still unchanged.

The required master-password verifier is PBKDF2-HMAC-SHA256 with a random salt. It is a UI gate, not encryption key material, and the password itself is never stored. Because encryption-at-rest uses Windows DPAPI, Windows account security remains essential; the app-level lock is not a defense against code already running as the signed-in Windows user.

## Exports and backups

Safe JSON and collection exports keep secret-field metadata but set secret values to `null` and mark them redacted. Updating from a redacted export preserves an existing matching secret rather than blanking it.

Portable full backups use Scrypt (`N=32768`, `r=8`, `p=1`) to derive a key and AES-256-GCM for authenticated encryption. Local rolling backups use the DPAPI-protected vault key. SQLite snapshots and integrity validation are performed in memory; plaintext database snapshots are not written to temporary files.

## Files and diagnostics

Data is stored under the current user's `%LOCALAPPDATA%\RVB Vault` profile directory and inherits its Windows access controls. Crash logs contain exception diagnostics only; application code does not log entry or secret values.
