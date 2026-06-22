"""
workwell/tests/test_phase6.py

Phase 6 test suite — Settings, Config & Session Logging.

Tests are grouped into two classes:
  TestSessionLogger  — unit tests for the SQLite logger (no Qt required)
  TestSettingsWindow — smoke tests for the settings UI (requires QApplication)

Run with:
    python -m pytest tests/test_phase6.py -v
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest


# ══════════════════════════════════════════════════════════════════════════════
# SessionLogger tests  (no Qt dependency)
# ══════════════════════════════════════════════════════════════════════════════

class TestSessionLogger:
    """Unit-tests for src.db.session_log.SessionLogger."""

    @pytest.fixture()
    def tmp_db(self, tmp_path: Path):
        """Return a SessionLogger backed by a temp SQLite file."""
        from src.db.session_log import SessionLogger
        db = SessionLogger(tmp_path / "test_sessions.db")
        yield db
        db.close()

    # ── Basic insert / read ───────────────────────────────────────────────────

    def test_reminder_shown_is_recorded(self, tmp_db):
        tmp_db.log_reminder_shown(active_minutes=35)
        rows = tmp_db.get_recent(limit=10)
        assert len(rows) == 1
        assert rows[0]["event"] == "reminder_shown"
        assert rows[0]["active_minutes"] == 35

    def test_break_taken_is_recorded(self, tmp_db):
        tmp_db.log_break_taken(active_minutes=40)
        rows = tmp_db.get_recent()
        assert rows[0]["event"] == "break_taken"

    def test_skipped_is_recorded(self, tmp_db):
        tmp_db.log_skipped(active_minutes=42)
        rows = tmp_db.get_recent()
        assert rows[0]["event"] == "skipped"

    def test_multiple_events_ordered_newest_first(self, tmp_db):
        tmp_db.log_reminder_shown(10)
        tmp_db.log_break_taken(12)
        tmp_db.log_skipped(15)
        rows = tmp_db.get_recent(limit=5)
        assert len(rows) == 3
        # newest-first → last inserted is index 0
        assert rows[0]["event"] == "skipped"
        assert rows[1]["event"] == "break_taken"
        assert rows[2]["event"] == "reminder_shown"

    # ── Summary stats ─────────────────────────────────────────────────────────

    def test_empty_summary(self, tmp_db):
        stats = tmp_db.get_summary()
        assert stats["total_reminders"] == 0
        assert stats["total_breaks"] == 0
        assert stats["total_skips"] == 0
        assert stats["break_rate"] == 0.0
        assert stats["first_event_ts"] is None

    def test_summary_counts(self, tmp_db):
        tmp_db.log_reminder_shown(30)
        tmp_db.log_break_taken(31)
        tmp_db.log_reminder_shown(65)
        tmp_db.log_skipped(66)
        stats = tmp_db.get_summary()
        assert stats["total_reminders"] == 2
        assert stats["total_breaks"] == 1
        assert stats["total_skips"] == 1

    def test_break_rate_calculation(self, tmp_db):
        # 3 break-taken, 1 skipped → rate = 3/4 = 0.75
        for i in range(3):
            tmp_db.log_break_taken(30 + i)
        tmp_db.log_skipped(35)
        stats = tmp_db.get_summary()
        assert abs(stats["break_rate"] - 0.75) < 1e-9

    def test_break_rate_zero_when_no_responses(self, tmp_db):
        tmp_db.log_reminder_shown(30)   # only a show, no response logged
        stats = tmp_db.get_summary()
        assert stats["break_rate"] == 0.0

    # ── Limit on get_recent ───────────────────────────────────────────────────

    def test_get_recent_limit(self, tmp_db):
        for i in range(20):
            tmp_db.log_reminder_shown(i)
        rows = tmp_db.get_recent(limit=5)
        assert len(rows) == 5

    # ── Persistence: close and reopen ────────────────────────────────────────

    def test_data_persists_across_reconnect(self, tmp_path):
        from src.db.session_log import SessionLogger
        db_path = tmp_path / "persist.db"

        logger1 = SessionLogger(db_path)
        logger1.log_break_taken(30)
        logger1.log_skipped(35)
        logger1.close()

        logger2 = SessionLogger(db_path)
        rows = logger2.get_recent()
        logger2.close()

        assert len(rows) == 2

    # ── Thread safety (basic smoke test) ─────────────────────────────────────

    def test_concurrent_writes(self, tmp_db):
        import threading

        errors: list[Exception] = []

        def worker(n: int) -> None:
            try:
                for i in range(10):
                    tmp_db.log_reminder_shown(n * 10 + i)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        stats = tmp_db.get_summary()
        assert stats["total_reminders"] == 50


# ══════════════════════════════════════════════════════════════════════════════
# SettingsWindow tests  (requires QApplication)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def qt_app():
    """Module-scoped QApplication — created once for all Qt tests."""
    from PyQt6.QtWidgets import QApplication
    existing = QApplication.instance()
    if existing:
        yield existing
    else:
        a = QApplication(sys.argv)
        yield a


class TestSettingsWindow:
    """Smoke-tests for the SettingsWindow dialog."""

    @pytest.fixture()
    def default_config(self) -> dict:
        return {
            "reminder": {
                "interval_minutes": 35,
                "idle_reset_minutes": 5,
                "snooze_minutes": 15,
            },
            "startup": {"launch_on_boot": True},
            "appearance": {"theme": "dark"},
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

    @pytest.fixture()
    def window(self, qt_app, default_config):
        from src.ui.settings_window import SettingsWindow
        win = SettingsWindow(default_config)
        yield win
        win.close()

    # ── Construction ──────────────────────────────────────────────────────────

    def test_window_creates_without_error(self, window):
        assert window is not None

    def test_window_has_correct_title(self, window):
        assert "Settings" in window.windowTitle()

    # ── Values loaded correctly ───────────────────────────────────────────────

    def test_interval_spin_loaded(self, window):
        assert window._spin_interval.value() == 35

    def test_idle_spin_loaded(self, window):
        assert window._spin_idle.value() == 5

    def test_snooze_spin_loaded(self, window):
        assert window._spin_snooze.value() == 15

    def test_boot_checkbox_loaded(self, window):
        assert window._chk_boot.isChecked() is True

    def test_theme_combo_loaded(self, window):
        assert window._cmb_theme.currentText() == "dark"

    def test_log_enabled_loaded(self, window):
        assert window._chk_log_enabled.isChecked() is True

    def test_ai_disabled_loaded(self, window):
        assert window._chk_ai.isChecked() is False

    # ── settings_saved signal ─────────────────────────────────────────────────

    def test_save_emits_signal(self, qt_app, default_config):
        from src.ui.settings_window import SettingsWindow
        received: list[dict] = []
        win = SettingsWindow(default_config)
        win.settings_saved.connect(received.append)

        # Change interval and save
        win._spin_interval.setValue(45)
        win._on_save()

        assert len(received) == 1
        assert received[0]["reminder"]["interval_minutes"] == 45
        win.close()

    def test_cancel_does_not_emit_signal(self, qt_app, default_config):
        from src.ui.settings_window import SettingsWindow
        received: list[dict] = []
        win = SettingsWindow(default_config)
        win.settings_saved.connect(received.append)

        win.reject()  # simulates Cancel

        assert received == []
        win.close()

    def test_all_keys_present_in_saved_config(self, qt_app, default_config):
        from src.ui.settings_window import SettingsWindow
        received: list[dict] = []
        win = SettingsWindow(default_config)
        win.settings_saved.connect(received.append)
        win._on_save()

        cfg = received[0]
        assert "reminder"     in cfg
        assert "startup"      in cfg
        assert "appearance"   in cfg
        assert "ai_assistant" in cfg
        assert "logging"      in cfg
        win.close()

    # ── Theme preview ─────────────────────────────────────────────────────────

    def test_theme_switch_to_light_applies_qss(self, window):
        window._cmb_theme.setCurrentText("light")
        qss = window.styleSheet()
        assert "f5f5f5" in qss or "#f5f5f5" in qss   # light background

    def test_theme_switch_to_dark_applies_qss(self, window):
        window._cmb_theme.setCurrentText("dark")
        qss = window.styleSheet()
        assert "1a1a2e" in qss or "#1a1a2e" in qss    # dark background


# ══════════════════════════════════════════════════════════════════════════════
# Config persistence tests  (paths.py load/save round-trip)
# ══════════════════════════════════════════════════════════════════════════════

class TestConfigPersistence:
    """Verify save_config → load_config round-trip fidelity."""

    def test_save_and_reload(self, tmp_path, monkeypatch):
        """save_config writes valid JSON that load_config can reload."""
        import src.utils.paths as paths_mod

        # Redirect the app-data root to a temp directory
        monkeypatch.setattr(
            paths_mod, "_get_app_data_root", lambda: tmp_path / "WorkWell"
        )
        paths_mod.ensure_app_dirs()

        cfg = {
            "reminder": {"interval_minutes": 50},
            "startup": {"launch_on_boot": False},
        }
        paths_mod.save_config(cfg)

        loaded = paths_mod.load_config()
        assert loaded["reminder"]["interval_minutes"] == 50
        assert loaded["startup"]["launch_on_boot"] is False

    def test_defaults_merged_on_load(self, tmp_path, monkeypatch):
        """Keys missing from disk are filled in from built-in defaults."""
        import src.utils.paths as paths_mod

        monkeypatch.setattr(
            paths_mod, "_get_app_data_root", lambda: tmp_path / "WorkWell2"
        )
        paths_mod.ensure_app_dirs()

        # Write a minimal config — no "appearance" key
        minimal = {"reminder": {"interval_minutes": 20}}
        paths_mod.save_config(minimal)

        loaded = paths_mod.load_config()
        # "appearance" should come from _DEFAULTS
        assert "appearance" in loaded
        assert "theme" in loaded["appearance"]

    def test_corrupt_config_falls_back_to_defaults(self, tmp_path, monkeypatch):
        """Corrupt JSON on disk falls back to defaults without crashing."""
        import src.utils.paths as paths_mod

        monkeypatch.setattr(
            paths_mod, "_get_app_data_root", lambda: tmp_path / "WorkWell3"
        )
        paths_mod.ensure_app_dirs()

        # Write garbage
        cfg_path = paths_mod.get_config_path()
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text("not valid json }{", encoding="utf-8")

        loaded = paths_mod.load_config()
        assert "reminder" in loaded   # default keys present
