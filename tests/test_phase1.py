"""
workwell/tests/test_phase1.py

Phase 1 tests — project setup & foundation.
Run with:  python -m pytest tests/ -v
"""

import json
import sys
import logging
import tempfile
import os
from pathlib import Path

# Make sure src is importable from the tests/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.paths import (
    get_platform,
    get_app_data_dir,
    get_log_dir,
    get_config_file,
    get_project_root,
    load_config,
    save_config,
    _deep_merge,
)
from src.utils.logger import setup_logging, get_logger
from src.core.constants import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_REMINDER_INTERVAL_MINUTES,
    DEFAULT_IDLE_RESET_MINUTES,
    ROTATING_FACTS,
    HEALTH_TIPS,
)


# ── Platform detection ───────────────────────────────────────────────────────

def test_get_platform_returns_known_value():
    platform = get_platform()
    assert platform in ("windows", "linux", "macos"), f"Unknown platform: {platform}"


def test_get_platform_matches_sys_platform():
    import sys as _sys
    platform = get_platform()
    if _sys.platform.startswith("win"):
        assert platform == "windows"
    elif _sys.platform.startswith("darwin"):
        assert platform == "macos"
    else:
        assert platform == "linux"


# ── Path resolution ──────────────────────────────────────────────────────────

def test_app_data_dir_is_absolute():
    assert get_app_data_dir().is_absolute()


def test_log_dir_is_absolute():
    assert get_log_dir().is_absolute()


def test_config_file_has_json_extension():
    assert get_config_file().suffix == ".json"


def test_project_root_contains_main():
    root = get_project_root()
    assert (root / "main.py").exists(), "main.py not found at project root"


def test_project_root_contains_requirements():
    root = get_project_root()
    assert (root / "requirements.txt").exists()


# ── Default config ────────────────────────────────────────────────────────────

def test_default_config_is_valid_json():
    defaults = get_project_root() / "config" / "defaults.json"
    assert defaults.exists(), "defaults.json missing"
    with open(defaults) as f:
        data = json.load(f)
    assert isinstance(data, dict)


def test_default_config_has_required_sections():
    defaults = get_project_root() / "config" / "defaults.json"
    with open(defaults) as f:
        data = json.load(f)
    for section in ("reminder", "startup", "appearance", "ai_assistant", "logging"):
        assert section in data, f"Missing section: {section}"


def test_default_reminder_interval():
    defaults = get_project_root() / "config" / "defaults.json"
    with open(defaults) as f:
        data = json.load(f)
    assert data["reminder"]["interval_minutes"] == DEFAULT_REMINDER_INTERVAL_MINUTES


# ── Config load / save / merge ────────────────────────────────────────────────

def test_load_config_returns_dict():
    config = load_config()
    assert isinstance(config, dict)


def test_load_config_has_all_sections():
    config = load_config()
    for section in ("reminder", "startup", "appearance", "ai_assistant", "logging"):
        assert section in config


def test_deep_merge_overrides_leaf():
    base = {"a": {"b": 1, "c": 2}}
    override = {"a": {"b": 99}}
    result = _deep_merge(base, override)
    assert result["a"]["b"] == 99
    assert result["a"]["c"] == 2


def test_deep_merge_adds_new_key():
    base = {"x": 1}
    override = {"y": 2}
    result = _deep_merge(base, override)
    assert result["x"] == 1
    assert result["y"] == 2


def test_save_and_reload_config(tmp_path, monkeypatch):
    """save_config writes to disk; load_config reads it back."""
    monkeypatch.setattr("src.utils.paths.get_config_file", lambda: tmp_path / "config.json")
    monkeypatch.setattr("src.utils.paths.get_app_data_dir", lambda: tmp_path)

    config = load_config()
    config["reminder"]["interval_minutes"] = 42
    save_config(config)

    loaded = json.loads((tmp_path / "config.json").read_text())
    assert loaded["reminder"]["interval_minutes"] == 42


# ── Logging ───────────────────────────────────────────────────────────────────

def test_setup_logging_creates_log_file(tmp_path):
    import src.utils.logger as logger_mod
    logger_mod._initialized = False           # reset singleton for test

    setup_logging(tmp_path, level="DEBUG")
    log_file = tmp_path / "workwell.log"
    assert log_file.exists(), "Log file was not created"

    logger_mod._initialized = False           # clean up for other tests


def test_get_logger_returns_logger():
    logger = get_logger("test_module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_module"


# ── Constants ─────────────────────────────────────────────────────────────────

def test_app_name_is_string():
    assert isinstance(APP_NAME, str) and len(APP_NAME) > 0


def test_app_version_semver():
    parts = APP_VERSION.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_rotating_facts_not_empty():
    assert len(ROTATING_FACTS) >= 5
    for fact in ROTATING_FACTS:
        assert isinstance(fact, str) and len(fact) > 10


def test_health_tips_structure():
    assert len(HEALTH_TIPS) >= 5
    for tip in HEALTH_TIPS:
        assert "title" in tip and "body" in tip
        assert isinstance(tip["title"], str)
        assert isinstance(tip["body"], str)


def test_default_interval_positive():
    assert DEFAULT_REMINDER_INTERVAL_MINUTES > 0
    assert DEFAULT_IDLE_RESET_MINUTES > 0
