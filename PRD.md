# RVB Vault 1.2.0 — concise PRD and implementation plan

## Product goal

Make saved text immediately retrievable and safely copyable from a polished Windows desktop interface. The primary success path is: invoke search, type a few characters, choose a result, copy the needed value, and return to the current app.

## Users and jobs

- Developers and operators retrieving SSH commands, paths, URLs, and multi-step procedures.
- Knowledge workers reusing long prompts and structured snippets.
- Individuals storing credentials locally with masking, encryption, auto-lock, and clipboard hygiene.

## Version 1 scope

- Three-pane compact desktop UI: category navigation, searchable results, detail/editor.
- Light, dark, and system appearance; restrained frosted neutral surfaces and best-effort Windows blur.
- Default categories: Prompts, SSH Commands, Passwords; unlimited custom categories with safe rename, reorder, and delete.
- Entries with title, tags, notes, favorite status, typed custom fields, secret masking, usage timestamps/counts, duplicate and delete.
- FTS5 search over title, tags, notes, and non-secret field values only.
- One-click field copy, template variable resolution, copy-entire-entry, and ordered procedure steps.
- Reusable Group Fields / Command Builders containing unlimited ordered fixed and editable segments, with exact whitespace preservation, a structure editor, runtime inputs, live preview, and one-click assembled-output copying.
- Password generation, Windows Hello-first vault lock, 15-minute default inactivity lock, Windows lock/sleep awareness, and configurable secret clipboard clearing.
- Quick search dialog, `Ctrl+Shift+Space` global hotkey where Windows permits, keyboard shortcuts, and system tray.
- Local SQLite storage, encrypted automatic rolling backups, recovery-password full backups, secret-redacted safe exports, and previewed collection imports with duplicate handling.
- Settings and About screens; PyInstaller one-directory build configuration.

## Non-goals

- Cloud sync, browser extensions, collaboration, telemetry, localhost services, or mobile clients.
- Cross-device decryption of Windows-bound rolling backups. Portable recovery-password backups cover deliberate transfer and disaster recovery.

## Quality and acceptance

- No secret plaintext in SQLite search tables.
- A category with entries cannot be deleted without choosing a safe destination.
- Clipboard timers do not erase content copied later by another app.
- All data-changing operations are transactional.
- App launches without network access and initializes a fresh data directory.
- Automated tests cover schema/defaults, CRUD/FTS secrecy, encryption, backup/restore, and settings helpers.

## Implementation sequence

1. Data paths, settings, DPAPI-backed encryption, schema, repositories, and FTS indexing.
2. Backup/import/export and clipboard/template services.
3. Qt shell, theme system, category/results/editor flows, quick search, tray, locking, and shortcuts.
4. Automated tests, headless smoke launch, PyInstaller configuration, and build documentation.

## Project structure

```text
src/rvb_vault/
  app.py                  application bootstrap and lock controller
  db.py                   SQLite schema, migrations, CRUD, and FTS
  security.py             DPAPI-backed key storage and AES-GCM
  backup.py               encrypted backups and JSON transfer
  settings.py             typed QSettings access
  hotkey.py               Windows global hotkey integration
  ui/
    main_window.py        three-pane shell and interactions
    editor.py             entry editor and dynamic fields
    dialogs.py            settings, lock, category and about dialogs
    quick_search.py       keyboard-first search overlay
    theme.py              light/dark tokens and Windows blur
tests/                    service and persistence tests
scripts/smoke_test.py     headless launch and critical flow check
```
