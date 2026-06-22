"""
workwell/src/utils/paths.py

Centralised path resolution for WorkWell.

All platform-specific data directories are resolved here so the rest of
the codebase never needs to import os.path or platformdirs directly.

Directory layout (XDG / platform-aware)
----------------------------------------
  Linux   : ~/.local/share/WorkWell/
  Windows : %APPDATA%\\WorkWell\\
  macOS   : ~/Library/Application Support/WorkWell/

Sub-directories
  logs/   — rotating log files
  data/   — SQLite databases, future persistent data files

Public API
----------
  ensure_app_dirs()          create all required directories on first run
  get_log_dir()   -> Path    path to the logs/ sub-directory
  get_data_dir()  -> Path    path to the data/ sub-directory  ← Phase 6
  get_config_path() -> Path  path to the user config JSON file
  load_config()   -> dict    load + merge with defaults
  save_config(cfg)           write config back to disk (atomic)
"""

from __future__ import annotations

import json
import os
import platform
import tempfile
from pathlib import Path
from typing import Any

from src.core.constants import APP_NAME

# ── Default config (mirrors config/defaults.json) ────────────────────────────
_DEFAULTS: dict[str, Any] = {
    "reminder": {
        "interval_minutes": 35,
        "enabled": True,
        "idle_reset_minutes": 5,
        "snooze_minutes": 15,
    },
    "startup": {
        "launch_on_boot": True,
        "minimize_to_tray": True,
    },
    "appearance": {
        "theme": "dark",
        "popup_opacity": 0.92,
    },
    "ai_assistant": {
        "enabled": False,
        "provider": "openai",
        "api_key": "",
        "model": "gpt-4o-mini",
    },
    "logging": {
        "enabled": True,
        "log_level": "INFO",
        "log_responses": True,
    },
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_app_data_root() -> Path:
    """Return the platform-appropriate user data directory for WorkWell."""
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        # Linux / BSD — honour XDG_DATA_HOME
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_NAME


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into a copy of *base*."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def get_platform() -> str:
    """Return a normalised platform string: 'windows', 'linux', or 'macos'."""
    system = platform.system()
    if system == "Windows":
        return "windows"
    if system == "Darwin":
        return "macos"
    return "linux"


def get_app_data_dir() -> Path:
    """Return the root app-data directory (alias for _get_app_data_root)."""
    return _get_app_data_root()


def get_config_file() -> Path:
    """Return the user config JSON path (alias for get_config_path)."""
    return get_config_path()


def get_project_root() -> Path:
    """Return the project root directory (the folder that contains main.py)."""
    return Path(__file__).parent.parent.parent


def get_assets_dir() -> Path:
    """Return the assets/ directory inside the project root."""
    return get_project_root() / "assets"


def get_log_dir() -> Path:
    """Return the path to the logs/ directory (not guaranteed to exist yet)."""
    return _get_app_data_root() / "logs"


def get_data_dir() -> Path:
    """Return the path to the data/ directory used for SQLite DBs etc.

    Added in Phase 6.  Always call ensure_app_dirs() on startup to guarantee
    this directory exists before attempting to open a database.
    """
    return _get_app_data_root() / "data"


def get_config_path() -> Path:
    """Return the path to the user-level config JSON file."""
    return _get_app_data_root() / "config.json"


def ensure_app_dirs() -> None:
    """Create all required application directories if they do not exist.

    Safe to call repeatedly — uses mkdir(exist_ok=True).
    """
    get_log_dir().mkdir(parents=True, exist_ok=True)
    get_data_dir().mkdir(parents=True, exist_ok=True)   # ← Phase 6
    # config.json sits in the root; the root is created by the above calls


def load_config() -> dict[str, Any]:
    """Load the user config, deep-merging on top of built-in defaults.

    If the config file does not exist or is malformed, the defaults are
    returned and a fresh config file is written to disk.
    """
    cfg_path = get_config_path()

    # Try to load existing config
    user_cfg: dict[str, Any] = {}
    if cfg_path.exists():
        try:
            with cfg_path.open("r", encoding="utf-8") as fh:
                user_cfg = json.load(fh)
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable — fall back to defaults
            user_cfg = {}

    # Also load defaults.json from the project config/ directory if present
    project_defaults_path = Path(__file__).parent.parent.parent / "config" / "defaults.json"
    project_defaults: dict[str, Any] = {}
    if project_defaults_path.exists():
        try:
            with project_defaults_path.open("r", encoding="utf-8") as fh:
                project_defaults = json.load(fh)
        except (json.JSONDecodeError, OSError):
            project_defaults = {}

    # Merge: built-in _DEFAULTS → project defaults → user config
    merged = _deep_merge(_DEFAULTS, project_defaults)
    merged = _deep_merge(merged, user_cfg)

    # Write back if the file didn't exist yet (first-run initialisation)
    if not cfg_path.exists():
        save_config(merged)

    return merged


def save_config(config: dict[str, Any]) -> None:
    """Atomically write *config* to the user config JSON file.

    Uses a temp file + rename so a crash mid-write never corrupts the config.
    """
    cfg_path = get_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temp file in the same directory, then rename
    fd, tmp_path = tempfile.mkstemp(
        dir=cfg_path.parent, prefix=".config_tmp_", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(config, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        Path(tmp_path).replace(cfg_path)
    except OSError:
        # Clean up the temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
