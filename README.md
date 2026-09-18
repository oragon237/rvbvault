# RVB Vault

RVB Vault is a local-first Windows productivity vault for prompts, commands, procedures, credentials, and frequently copied text. It replaces the repeated “find, highlight, copy, paste” workflow with keyboard-first search and one-click copy actions.

Version 1.2 adds safe secret-redacted exports, password-encrypted portable backups, previewed collection imports with duplicate handling, fully ordered procedure steps, Windows Hello unlock, Windows session locking, and local-time metadata.

## Run from source

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m rvb_vault
```

The application stores its data in `%LOCALAPPDATA%\RVB Vault` by default. Set `RVB_VAULT_DATA_DIR` to use a different directory for development or tests.

## Verification

```powershell
python -m unittest discover -s tests -v
python scripts/smoke_test.py
```

## Windows build

```powershell
.\build.ps1
```

The build script installs PyInstaller, runs the test suite, and produces `dist\RVB Vault\RVB Vault.exe`. The app is intentionally built in one-directory mode so Qt plugins remain inspectable and startup is faster.

## Security model

- Secret field values are encrypted with AES-256-GCM.
- On Windows, the AES key is itself protected with Windows DPAPI for the current user.
- Secret values are never written to the FTS5 index.
- Clipboard clearing only occurs when the clipboard still contains the value RVB Vault copied.
- Windows Hello / Windows Security performs primary vault authentication; RVB Vault never receives the Windows PIN or biometric data. A PBKDF2 verifier can be configured as a fallback.
- Safe JSON exports preserve structure but always redact secret values. Imports accept those redactions without exposing or silently replacing existing secrets.
- Portable full `.rvbbackup` files use Scrypt-derived AES-256-GCM encryption and require their recovery password. Automatic rolling backups remain protected by the Windows-account-bound local key.
- Backup snapshots and validation remain in memory, so decrypted database snapshots are not written to temporary files.

## Current platform notes

Global `Ctrl+Shift+Space` uses the Windows `RegisterHotKey` API and falls back to an app-local shortcut if another program owns it. Acrylic blur is best-effort and falls back to styled translucency. Windows Hello uses the native Windows consent verifier on Windows 10/11 and falls back to the optional RVB master password only when Hello is unavailable.
