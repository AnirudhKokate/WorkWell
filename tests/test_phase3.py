"""
workwell/tests/test_phase3.py

Phase 3 tests — System Tray & Startup Integration.
Run with:  python -m pytest tests/test_phase3.py -v
"""

import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject

from src.core.activity_monitor import SessionState
from src.ui.tray_manager import TrayManager
from src.utils import startup as startup_mod
from src.utils.startup import (
    _build_desktop_entry,
    _get_desktop_path,
    enable_startup,
    disable_startup,
    is_startup_enabled,
)


# ── Qt app fixture ────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def base_config():
    return {
        "reminder": {
            "interval_minutes": 35,
            "idle_reset_minutes": 5,
            "snooze_minutes": 15,
            "enabled": True,
        },
        "startup": {"launch_on_boot": True},
        "appearance": {"theme": "dark"},
        "ai_assistant": {"enabled": False},
        "logging": {"log_level": "INFO"},
    }


# ── TrayManager construction ──────────────────────────────────────────────────

def test_tray_manager_creates(qt_app, base_config):
    tray = TrayManager(base_config)
    assert tray is not None


def test_tray_manager_is_qobject(qt_app, base_config):
    tray = TrayManager(base_config)
    assert isinstance(tray, QObject)


def test_tray_manager_not_paused_initially(qt_app, base_config):
    tray = TrayManager(base_config)
    assert tray._paused is False


# ── update_session_state ──────────────────────────────────────────────────────

def test_update_session_state_active(qt_app, base_config):
    tray = TrayManager(base_config)
    state = SessionState(active_seconds=120.0, is_idle=False)
    tray.update_session_state(state)   # should not raise
    assert "2m" in tray._status_action.text() or "Active" in tray._status_action.text()


def test_update_session_state_idle(qt_app, base_config):
    tray = TrayManager(base_config)
    state = SessionState(active_seconds=60.0, is_idle=True, idle_seconds=30.0)
    tray.update_session_state(state)
    assert "idle" in tray._status_action.text().lower()


def test_update_session_state_paused(qt_app, base_config):
    tray = TrayManager(base_config)
    tray._paused = True
    state = SessionState(active_seconds=60.0, is_idle=False)
    tray.update_session_state(state)
    assert "paused" in tray._status_action.text().lower()


# ── set_paused ────────────────────────────────────────────────────────────────

def test_set_paused_true(qt_app, base_config):
    tray = TrayManager(base_config)
    tray.set_paused(True)
    assert tray._paused is True
    assert "Resume" in tray._pause_action.text()


def test_set_paused_false(qt_app, base_config):
    tray = TrayManager(base_config)
    tray.set_paused(True)
    tray.set_paused(False)
    assert tray._paused is False
    assert "Pause" in tray._pause_action.text()


# ── pause_toggled signal ──────────────────────────────────────────────────────

def test_pause_toggle_emits_signal(qt_app, base_config):
    tray = TrayManager(base_config)
    received = []
    tray.pause_toggled.connect(lambda p: received.append(p))
    tray._on_pause_toggled()
    assert received == [True]


def test_pause_toggle_twice_emits_false(qt_app, base_config):
    tray = TrayManager(base_config)
    received = []
    tray.pause_toggled.connect(lambda p: received.append(p))
    tray._on_pause_toggled()
    tray._on_pause_toggled()
    assert received == [True, False]


# ── quit_requested signal ─────────────────────────────────────────────────────

def test_quit_emits_signal(qt_app, base_config):
    tray = TrayManager(base_config)
    fired = []
    tray.quit_requested.connect(lambda: fired.append(True))
    tray._on_quit()
    assert len(fired) == 1


# ── show_popup_requested signal ───────────────────────────────────────────────

def test_show_popup_signal_wired(qt_app, base_config):
    tray = TrayManager(base_config)
    fired = []
    tray.show_popup_requested.connect(lambda: fired.append(True))
    tray.show_popup_requested.emit()
    assert len(fired) == 1


# ── Context menu items ────────────────────────────────────────────────────────

def test_menu_has_quit_action(qt_app, base_config):
    tray = TrayManager(base_config)
    texts = [a.text() for a in tray._menu.actions()]
    assert any("Quit" in t for t in texts)


def test_menu_has_pause_action(qt_app, base_config):
    tray = TrayManager(base_config)
    texts = [a.text() for a in tray._menu.actions()]
    assert any("Pause" in t or "Resume" in t for t in texts)


def test_menu_has_settings_action(qt_app, base_config):
    tray = TrayManager(base_config)
    texts = [a.text() for a in tray._menu.actions()]
    assert any("Settings" in t for t in texts)


def test_menu_has_show_reminder_action(qt_app, base_config):
    tray = TrayManager(base_config)
    texts = [a.text() for a in tray._menu.actions()]
    assert any("reminder" in t.lower() for t in texts)


# ── Linux desktop entry ───────────────────────────────────────────────────────

def test_desktop_entry_contains_required_fields():
    entry = _build_desktop_entry()
    assert "[Desktop Entry]" in entry
    assert "Type=Application" in entry
    assert "Name=WorkWell" in entry
    assert "Exec=" in entry
    assert "Terminal=false" in entry
    assert "X-GNOME-Autostart-enabled=true" in entry


def test_desktop_entry_exec_contains_main_py():
    entry = _build_desktop_entry()
    assert "main.py" in entry


def test_desktop_path_is_under_autostart():
    path = _get_desktop_path()
    assert "autostart" in str(path)
    assert path.suffix == ".desktop"


# ── enable / disable / check startup (Linux, patched) ────────────────────────

def test_enable_linux_startup(tmp_path, monkeypatch):
    monkeypatch.setattr(startup_mod, "_get_desktop_path",
                        lambda: tmp_path / "autostart" / "workwell.desktop")
    ok, msg = enable_startup()
    assert ok is True
    assert (tmp_path / "autostart" / "workwell.desktop").exists()


def test_disable_linux_startup(tmp_path, monkeypatch):
    desktop = tmp_path / "autostart" / "workwell.desktop"
    desktop.parent.mkdir(parents=True)
    desktop.write_text("[Desktop Entry]\n")
    monkeypatch.setattr(startup_mod, "_get_desktop_path", lambda: desktop)
    ok, msg = disable_startup()
    assert ok is True
    assert not desktop.exists()


def test_disable_linux_startup_when_not_present(tmp_path, monkeypatch):
    monkeypatch.setattr(startup_mod, "_get_desktop_path",
                        lambda: tmp_path / "autostart" / "workwell.desktop")
    ok, msg = disable_startup()
    assert ok is True   # graceful no-op


def test_is_startup_enabled_false_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(startup_mod, "_get_desktop_path",
                        lambda: tmp_path / "autostart" / "workwell.desktop")
    monkeypatch.setattr(startup_mod, "get_platform", lambda: "linux")
    assert is_startup_enabled() is False


def test_is_startup_enabled_true_when_present(tmp_path, monkeypatch):
    desktop = tmp_path / "autostart" / "workwell.desktop"
    desktop.parent.mkdir(parents=True)
    desktop.write_text("[Desktop Entry]\n")
    monkeypatch.setattr(startup_mod, "_get_desktop_path", lambda: desktop)
    monkeypatch.setattr(startup_mod, "get_platform", lambda: "linux")
    assert is_startup_enabled() is True


def test_enable_startup_creates_parent_dirs(tmp_path, monkeypatch):
    deep = tmp_path / "a" / "b" / "c" / "workwell.desktop"
    monkeypatch.setattr(startup_mod, "_get_desktop_path", lambda: deep)
    ok, _ = enable_startup()
    assert ok is True
    assert deep.exists()


# ── Unsupported platform graceful handling ────────────────────────────────────

def test_unsupported_platform_enable(monkeypatch):
    monkeypatch.setattr(startup_mod, "get_platform", lambda: "macos")
    ok, msg = enable_startup()
    assert ok is False
    assert "not supported" in msg.lower()


def test_unsupported_platform_disable(monkeypatch):
    monkeypatch.setattr(startup_mod, "get_platform", lambda: "macos")
    ok, msg = disable_startup()
    assert ok is False
