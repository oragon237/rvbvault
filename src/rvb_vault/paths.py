from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "RVB Vault"


def data_dir() -> Path:
    override = os.environ.get("RVB_VAULT_DATA_DIR")
    if override:
        root = Path(override).expanduser().resolve()
    elif os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
    else:
        root = Path.home() / ".local" / "share" / "rvb-vault"
    root.mkdir(parents=True, exist_ok=True)
    return root


def database_path() -> Path:
    return data_dir() / "vault.db"


def backups_dir() -> Path:
    path = data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def key_path() -> Path:
    return data_dir() / "vault.key"

