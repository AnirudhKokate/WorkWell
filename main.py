"""
workwell/main.py

Application entry point for WorkWell.

Run with:
    python main.py

Phase 1 — Skeleton: logging, config, Qt event loop
Phase 2 — Activity monitor wired in
Phase 3 — System tray icon + background daemon + startup integration
Phase 4 — Full-screen popup (replaces tray stub)
Phase 6 — Settings window, config persistence, SQLite session logging
Phase 7 — Polish, performance monitor, packaging prep  ← CURRENT
"""

import sys
import signal

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from src.utils.paths import (
    ensure_app_dirs,
    get_log_dir,
    get_data_dir,
    load_config,
    save_config,
)
from src.utils.logger import setup_logging, get_logger
from src.utils.startup import enable_startup, disable_startup, is_startup_enabled
from src.utils.perf_monitor import PerfMonitor                # ← Phase 7
from src.core.constants import APP_NAME, APP_VERSION
from src.core.activity_monitor import ActivityMonitor, SessionState
from src.ui.tray_manager import TrayManager
from src.ui.reminder_popup import ReminderPopup
from src.ui.settings_window import SettingsWindow
from src.db.session_log import SessionLogger


def _handle_sigint(*_args) -> None:
    log = get_logger(__name__)
    log.info("SIGINT received — shutting down.")
    QApplication.quit()


def main() -> int:
    # ── 1. Bootstrap ─────────────────────────────────────────────────────────
    ensure_app_dirs()
    config = load_config()
    setup_logging(
        log_dir=get_log_dir(),
        level=config.get("logging", {}).get("log_level", "INFO"),
    )
    log = get_logger(__name__)

    log.info("=" * 60)
    log.info("  %s  v%s  starting up", APP_NAME, APP_VERSION)
    log.info("=" * 60)

    # ── 2. QApplication ───────────────────────────────────────────────────────
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)

    # ── 3. Graceful Ctrl-C ────────────────────────────────────────────────────
    signal.signal(signal.SIGINT, _handle_sigint)
    sigint_timer = QTimer()
    sigint_timer.start(500)
    sigint_timer.timeout.connect(lambda: None)

    # ── 4. Performance monitor (Phase 7) ──────────────────────────────────────
    perf = PerfMonitor(interval_secs=10.0)
    perf.start()

    # ── 5. Session logger ─────────────────────────────────────────────────────
    db_path = get_data_dir() / "sessions.db"
    session_logger = SessionLogger(db_path)
    _logging_enabled = config.get("logging", {}).get("enabled", True)
    _log_responses   = config.get("logging", {}).get("log_responses", True)

    def _maybe_log(method_name: str, active_minutes: int) -> None:
        if not _logging_enabled:
            return
        getattr(session_logger, method_name)(active_minutes)

    # ── 6. Activity monitor ───────────────────────────────────────────────────
    monitor = ActivityMonitor(config)

    # ── 7. Reminder popup ─────────────────────────────────────────────────────
    popup = ReminderPopup(elapsed_minutes=0)

    def _on_reminder(state: SessionState) -> None:
        elapsed_min = int(state.active_seconds / 60)
        log.info("Reminder triggered — active for %d min.", elapsed_min)
        popup.show_popup(elapsed_minutes=elapsed_min)
        _maybe_log("log_reminder_shown", elapsed_min)

    def _on_break_taken() -> None:
        monitor.record_break_taken()
        if _log_responses:
            elapsed_min = int(monitor.get_state().active_seconds / 60)
            _maybe_log("log_break_taken", elapsed_min)

    def _on_skipped() -> None:
        monitor.record_break_skipped()
        if _log_responses:
            elapsed_min = int(monitor.get_state().active_seconds / 60)
            _maybe_log("log_skipped", elapsed_min)

    monitor.reminder_triggered.connect(_on_reminder)
    popup.break_taken.connect(_on_break_taken)
    popup.skipped.connect(_on_skipped)

    # ── 8. System tray ────────────────────────────────────────────────────────
    tray = TrayManager(config)
    tray.show()

    def _on_pause_toggled(paused: bool) -> None:
        monitor.set_enabled(not paused)

    def _on_show_popup_requested() -> None:
        elapsed_min = int(monitor.get_state().active_seconds / 60)
        popup.show_popup(elapsed_minutes=elapsed_min)

    tray.quit_requested.connect(QApplication.quit)
    tray.pause_toggled.connect(_on_pause_toggled)
    tray.show_popup_requested.connect(_on_show_popup_requested)
    monitor.session_updated.connect(tray.update_session_state)

    # ── 9. Settings window ────────────────────────────────────────────────────
    settings_win = SettingsWindow(config)

    def _on_settings_requested() -> None:
        settings_win._config = config.copy()
        settings_win._load_values()
        settings_win.show()
        settings_win.raise_()
        settings_win.activateWindow()

    def _on_settings_saved(new_cfg: dict) -> None:
        nonlocal config, _logging_enabled, _log_responses

        old_interval = config.get("reminder", {}).get("interval_minutes")
        old_boot     = config.get("startup",  {}).get("launch_on_boot")

        config           = new_cfg
        _logging_enabled = new_cfg.get("logging", {}).get("enabled", True)
        _log_responses   = new_cfg.get("logging", {}).get("log_responses", True)

        save_config(config)
        log.info("Config saved to disk.")

        new_interval = new_cfg.get("reminder", {}).get("interval_minutes")
        if new_interval and new_interval != old_interval:
            monitor.update_config(new_cfg)
            log.info("Reminder interval updated to %d min.", new_interval)

        new_boot = new_cfg.get("startup", {}).get("launch_on_boot")
        if new_boot != old_boot:
            ok, msg = enable_startup() if new_boot else disable_startup()
            log.info("Startup registration: %s", msg)

    settings_win.settings_saved.connect(_on_settings_saved)

    if hasattr(tray, "settings_requested"):
        tray.settings_requested.connect(_on_settings_requested)

    monitor.start()

    # ── 10. Startup-on-boot registration ─────────────────────────────────────
    if config.get("startup", {}).get("launch_on_boot", True):
        if not is_startup_enabled():
            ok, msg = enable_startup()
            log.info("Startup registration: %s", msg)
        else:
            log.info("Startup already registered.")
    else:
        if is_startup_enabled():
            ok, msg = disable_startup()
            log.info("Startup removal: %s", msg)

    # ── 11. Console banner ────────────────────────────────────────────────────
    stats = session_logger.get_summary()
    perf_snap = perf.latest
    print(f"\n{'='*58}")
    print(f"  {APP_NAME} v{APP_VERSION}  [Phase 7 — Final]")
    print(f"  Reminder interval : {config['reminder']['interval_minutes']} min")
    print(f"  Startup on boot   : {config['startup']['launch_on_boot']}")
    print(f"  Session logging   : {'on' if _logging_enabled else 'off'}  ->  {db_path}")
    print(f"  Total reminders   : {stats['total_reminders']}")
    print(f"  Break rate        : {stats['break_rate']:.0%}")
    print(f"  RAM (startup)     : {perf_snap['rss_mb']:.1f} MB")
    print(f"{'='*58}")
    print("  Running in system tray. Right-click the tray icon.")
    print("  Press Ctrl-C to exit.\n")

    log.info("Phase 7 running — all systems active.")

    exit_code = app.exec()

    # ── 12. Clean shutdown ────────────────────────────────────────────────────
    perf.stop()
    session_logger.close()
    log.info("%s shut down cleanly.", APP_NAME)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
