"""
workwell/tests/test_phase7.py

Phase 7 test suite — Polish, Performance & Packaging Prep.

Tests are grouped into three classes:

  TestPerfMonitor      — unit tests for the CPU/RAM sampler (no Qt)
  TestCrossPlatform    — checks that paths / startup helpers work on the
                         current OS without raising (Windows + Linux)
  TestPackagingPrep    — verifies that the PyInstaller spec and all
                         packaging prerequisites are in place

Run with:
    python -m pytest tests/test_phase7.py -v
"""

from __future__ import annotations

import sys
import time
import platform
from pathlib import Path

import pytest


# ══════════════════════════════════════════════════════════════════════════════
# PerfMonitor tests  (no Qt dependency)
# ══════════════════════════════════════════════════════════════════════════════

class TestPerfMonitor:
    """Unit-tests for src.utils.perf_monitor.PerfMonitor."""

    @pytest.fixture()
    def monitor(self):
        from src.utils.perf_monitor import PerfMonitor
        mon = PerfMonitor(interval_secs=1.0)
        yield mon
        mon.stop()

    # ── Construction & start/stop ─────────────────────────────────────────────

    def test_creates_without_error(self, monitor):
        assert monitor is not None

    def test_latest_returns_dict(self, monitor):
        result = monitor.latest
        assert isinstance(result, dict)
        assert "cpu_pct"  in result
        assert "rss_mb"   in result

    def test_initial_values_are_floats(self, monitor):
        result = monitor.latest
        assert isinstance(result["cpu_pct"], float)
        assert isinstance(result["rss_mb"],  float)

    def test_start_does_not_raise(self, monitor):
        monitor.start()   # should not raise

    def test_double_start_is_safe(self, monitor):
        monitor.start()
        monitor.start()   # second call is a no-op

    def test_stop_before_start_is_safe(self):
        from src.utils.perf_monitor import PerfMonitor
        mon = PerfMonitor(interval_secs=1.0)
        mon.stop()        # should not raise

    # ── Sampling ─────────────────────────────────────────────────────────────

    def test_rss_mb_is_non_negative(self, monitor):
        monitor.start()
        time.sleep(1.5)
        assert monitor.latest["rss_mb"] >= 0.0

    def test_cpu_pct_is_non_negative(self, monitor):
        monitor.start()
        time.sleep(1.5)
        assert monitor.latest["cpu_pct"] >= 0.0

    def test_rss_mb_is_plausible(self, monitor):
        """WorkWell should use less than 500 MB RSS at idle."""
        monitor.start()
        time.sleep(1.5)
        assert monitor.latest["rss_mb"] < 500.0

    def test_latest_returns_independent_copy(self, monitor):
        """Mutating the returned dict must not affect the internal state."""
        monitor.start()
        time.sleep(1.5)
        snap1 = monitor.latest
        snap1["cpu_pct"] = 9999.0
        snap2 = monitor.latest
        assert snap2["cpu_pct"] != 9999.0

    def test_thread_is_daemon(self, monitor):
        """The sampler thread must be a daemon so it doesn't block shutdown."""
        monitor.start()
        assert monitor._thread is not None
        assert monitor._thread.daemon is True

    def test_stop_joins_thread(self, monitor):
        monitor.start()
        time.sleep(0.5)
        monitor.stop()
        assert not monitor._thread.is_alive()


# ══════════════════════════════════════════════════════════════════════════════
# Cross-platform smoke tests
# ══════════════════════════════════════════════════════════════════════════════

class TestCrossPlatform:
    """Verify path helpers and startup utilities work on the current OS."""

    # ── paths.py ─────────────────────────────────────────────────────────────

    def test_get_platform_returns_known_value(self):
        from src.utils.paths import get_platform
        result = get_platform()
        assert result in ("windows", "linux", "macos")

    def test_get_platform_matches_sys_platform(self):
        from src.utils.paths import get_platform
        result = get_platform()
        if sys.platform == "win32":
            assert result == "windows"
        elif sys.platform == "darwin":
            assert result == "macos"
        else:
            assert result == "linux"

    def test_get_app_data_dir_returns_path(self):
        from src.utils.paths import get_app_data_dir
        p = get_app_data_dir()
        assert isinstance(p, Path)
        assert "WorkWell" in str(p)

    def test_get_log_dir_returns_path(self):
        from src.utils.paths import get_log_dir
        p = get_log_dir()
        assert isinstance(p, Path)

    def test_get_data_dir_returns_path(self):
        from src.utils.paths import get_data_dir
        p = get_data_dir()
        assert isinstance(p, Path)

    def test_get_assets_dir_points_to_existing_folder(self):
        from src.utils.paths import get_assets_dir
        p = get_assets_dir()
        assert p.exists(), f"assets/ not found at {p}"

    def test_get_project_root_contains_main(self):
        from src.utils.paths import get_project_root
        root = get_project_root()
        assert (root / "main.py").exists(), f"main.py not found under {root}"

    def test_ensure_app_dirs_creates_dirs(self, tmp_path, monkeypatch):
        import src.utils.paths as paths_mod
        monkeypatch.setattr(
            paths_mod, "_get_app_data_root", lambda: tmp_path / "WorkWell"
        )
        paths_mod.ensure_app_dirs()
        assert paths_mod.get_log_dir().exists()
        assert paths_mod.get_data_dir().exists()

    # ── startup.py ───────────────────────────────────────────────────────────

    def test_is_startup_enabled_returns_bool(self):
        from src.utils.startup import is_startup_enabled
        result = is_startup_enabled()
        assert isinstance(result, bool)

    def test_enable_startup_returns_tuple(self):
        from src.utils.startup import enable_startup
        result = enable_startup()
        assert isinstance(result, tuple)
        assert len(result) == 2
        ok, msg = result
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    def test_disable_startup_returns_tuple(self):
        from src.utils.startup import disable_startup
        result = disable_startup()
        assert isinstance(result, tuple)
        ok, msg = result
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    # ── constants.py ─────────────────────────────────────────────────────────

    def test_app_name_is_string(self):
        from src.core.constants import APP_NAME
        assert isinstance(APP_NAME, str)
        assert len(APP_NAME) > 0

    def test_app_version_format(self):
        from src.core.constants import APP_VERSION
        parts = APP_VERSION.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_rotating_facts_non_empty(self):
        from src.core.constants import ROTATING_FACTS
        assert len(ROTATING_FACTS) >= 5

    def test_health_tips_have_required_keys(self):
        from src.core.constants import HEALTH_TIPS
        for tip in HEALTH_TIPS:
            assert "title" in tip
            assert "body"  in tip


# ══════════════════════════════════════════════════════════════════════════════
# Packaging prep tests
# ══════════════════════════════════════════════════════════════════════════════

class TestPackagingPrep:
    """Verify all packaging prerequisites are in place."""

    @pytest.fixture(autouse=True)
    def project_root(self):
        from src.utils.paths import get_project_root
        self.root = get_project_root()

    # ── Required files ────────────────────────────────────────────────────────

    def test_main_py_exists(self):
        assert (self.root / "main.py").exists()

    def test_requirements_txt_exists(self):
        assert (self.root / "requirements.txt").exists(), (
            "requirements.txt missing — needed for pip install and PyInstaller"
        )

    def test_spec_file_exists(self):
        assert (self.root / "workwell.spec").exists(), (
            "workwell.spec missing — run Phase 7 to create it"
        )

    def test_defaults_json_exists(self):
        assert (self.root / "config" / "defaults.json").exists()

    def test_tray_icon_exists(self):
        assert (self.root / "assets" / "icons" / "tray.png").exists()

    def test_tray_paused_icon_exists(self):
        assert (self.root / "assets" / "icons" / "tray_paused.png").exists()

    # ── requirements.txt content ──────────────────────────────────────────────

    def test_requirements_contains_pyqt6(self):
        text = (self.root / "requirements.txt").read_text(encoding="utf-8").lower()
        assert "pyqt6" in text

    def test_requirements_contains_pynput(self):
        text = (self.root / "requirements.txt").read_text(encoding="utf-8").lower()
        assert "pynput" in text

    # ── Package structure ─────────────────────────────────────────────────────

    def test_src_init_exists(self):
        assert (self.root / "src" / "__init__.py").exists()

    def test_src_core_init_exists(self):
        assert (self.root / "src" / "core" / "__init__.py").exists()

    def test_src_ui_init_exists(self):
        assert (self.root / "src" / "ui" / "__init__.py").exists()

    def test_src_utils_init_exists(self):
        assert (self.root / "src" / "utils" / "__init__.py").exists()

    def test_src_db_init_exists(self):
        assert (self.root / "src" / "db" / "__init__.py").exists()

    # ── Core modules importable ───────────────────────────────────────────────

    def test_import_activity_monitor(self):
        from src.core.activity_monitor import ActivityMonitor
        assert ActivityMonitor is not None

    def test_import_session_log(self):
        from src.db.session_log import SessionLogger
        assert SessionLogger is not None

    def test_import_settings_window(self):
        from src.ui.settings_window import SettingsWindow
        assert SettingsWindow is not None

    def test_import_perf_monitor(self):
        from src.utils.perf_monitor import PerfMonitor
        assert PerfMonitor is not None

    # ── spec file sanity check ────────────────────────────────────────────────

    def test_spec_references_main_py(self):
        spec_text = (self.root / "workwell.spec").read_text(encoding="utf-8")
        assert "main.py" in spec_text

    def test_spec_references_assets(self):
        spec_text = (self.root / "workwell.spec").read_text(encoding="utf-8")
        assert "assets" in spec_text

    def test_spec_console_is_false(self):
        spec_text = (self.root / "workwell.spec").read_text(encoding="utf-8")
        assert "console=False" in spec_text
