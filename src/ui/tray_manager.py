"""
workwell/src/ui/tray_manager.py

System tray icon and context menu for WorkWell.

Responsibilities:
  - Show a tray icon (active = green, paused = grey)
  - Context menu: status line, separator, Pause/Resume, Settings (Phase 6),
    About, separator, Quit
  - Bubble notification when the reminder fires (pre-popup fallback)
  - Relay Pause/Resume to the ActivityMonitor
  - Emit signals so main.py can react without tight coupling

The tray never owns the popup — it only signals that one is needed.
The popup is created and shown by main.py (Phase 4).
"""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QObject, pyqtSignal

from src.utils.logger import get_logger
from src.utils.paths import get_assets_dir
from src.core.constants import APP_NAME, APP_VERSION, TRAY_TOOLTIP
from src.core.activity_monitor import SessionState

log = get_logger(__name__)


def _load_icon(filename: str) -> QIcon:
    """Load an icon from assets/icons/. Falls back to a blank icon if missing."""
    path = get_assets_dir() / "icons" / filename
    if path.exists():
        return QIcon(str(path))
    log.warning("Icon not found: %s — using blank fallback.", path)
    return QIcon()


class TrayManager(QObject):
    """
    Owns the QSystemTrayIcon and its context menu.

    Signals:
        quit_requested      — user clicked Quit
        pause_toggled(bool) — user toggled Pause; True = now paused
        settings_requested  — user clicked Settings
        show_popup_requested— user clicked 'Show Reminder Now'
    """

    quit_requested       = pyqtSignal()
    pause_toggled        = pyqtSignal(bool)
    settings_requested   = pyqtSignal()
    show_popup_requested = pyqtSignal()

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._paused = False
        self._active_minutes: float = 0.0

        # ── Icons ─────────────────────────────────────────────────────────────
        self._icon_active = _load_icon("tray.png")
        self._icon_paused = _load_icon("tray_paused.png")

        # ── Tray icon ─────────────────────────────────────────────────────────
        self._tray = QSystemTrayIcon(self._icon_active, parent)
        self._tray.setToolTip(TRAY_TOOLTIP)

        # ── Context menu ──────────────────────────────────────────────────────
        self._menu = QMenu()
        self._build_menu()
        self._tray.setContextMenu(self._menu)

        # Left-click also opens the menu
        self._tray.activated.connect(self._on_tray_activated)

        log.info("TrayManager initialised.")

    # ── Public API ────────────────────────────────────────────────────────────

    def show(self) -> None:
        """Make the tray icon visible."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.warning("System tray is not available on this desktop.")
            return
        self._tray.show()
        log.info("Tray icon shown.")

    def hide(self) -> None:
        self._tray.hide()

    def update_session_state(self, state: SessionState) -> None:
        """Called every tick — updates the tooltip and status menu item."""
        self._active_minutes = state.active_seconds / 60
        mins = int(self._active_minutes)
        secs = int(state.active_seconds % 60)

        if state.is_idle:
            tooltip = f"{APP_NAME} — idle"
            status_text = "Status: idle"
        elif self._paused:
            tooltip = f"{APP_NAME} — paused"
            status_text = "Status: paused"
        else:
            tooltip = f"{APP_NAME} — active {mins}m {secs:02d}s"
            status_text = f"Active: {mins}m {secs:02d}s  |  Breaks: {state.breaks_taken}"

        self._tray.setToolTip(tooltip)
        self._status_action.setText(status_text)

    def show_reminder_notification(self, state: SessionState) -> None:
        """Show a tray bubble notification when the reminder fires."""
        mins = int(state.active_seconds / 60)
        self._tray.showMessage(
            APP_NAME,
            f"You've been active for {mins} min — time for a break!",
            QSystemTrayIcon.MessageIcon.Information,
            4000,   # ms
        )
        log.debug("Tray notification shown.")

    def set_paused(self, paused: bool) -> None:
        """Sync pause state (called externally, e.g. from settings)."""
        self._paused = paused
        self._update_pause_action()
        self._tray.setIcon(self._icon_paused if paused else self._icon_active)

    # ── Menu construction ─────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        m = self._menu

        # Status line (non-clickable)
        self._status_action = QAction("Active: 0m 00s", self)
        self._status_action.setEnabled(False)
        m.addAction(self._status_action)

        m.addSeparator()

        # Pause / Resume
        self._pause_action = QAction("Pause reminders", self)
        self._pause_action.triggered.connect(self._on_pause_toggled)
        m.addAction(self._pause_action)

        # Show reminder now (useful for testing)
        show_action = QAction("Show reminder now", self)
        show_action.triggered.connect(self.show_popup_requested.emit)
        m.addAction(show_action)

        m.addSeparator()

        # Settings (Phase 6)
        settings_action = QAction("⚙  Settings…", self)
        settings_action.triggered.connect(self.settings_requested.emit)
        m.addAction(settings_action)

        # About
        about_action = QAction(f"About {APP_NAME} v{APP_VERSION}", self)
        about_action.setEnabled(False)
        m.addAction(about_action)

        m.addSeparator()

        # Quit
        quit_action = QAction("Quit WorkWell", self)
        quit_action.triggered.connect(self._on_quit)
        m.addAction(quit_action)

    def _update_pause_action(self) -> None:
        self._pause_action.setText(
            "Resume reminders" if self._paused else "Pause reminders"
        )

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_pause_toggled(self) -> None:
        self._paused = not self._paused
        self._update_pause_action()
        self._tray.setIcon(self._icon_paused if self._paused else self._icon_active)
        log.info("Reminders %s via tray.", "paused" if self._paused else "resumed")
        self.pause_toggled.emit(self._paused)

    def _on_quit(self) -> None:
        log.info("Quit requested via tray menu.")
        self.quit_requested.emit()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Left-click opens the context menu (same as right-click)."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._tray.contextMenu().popup(
                self._tray.geometry().center()
            )
