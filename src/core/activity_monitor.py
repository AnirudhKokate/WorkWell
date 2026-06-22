"""
workwell/src/core/activity_monitor.py

The activity monitoring engine for WorkWell.

Responsibilities:
  - Listen for keyboard and mouse events globally (via pynput)
  - Track cumulative active time in the current sitting session
  - Detect idle periods and reset/pause the session timer
  - Detect when the user has been active long enough to trigger a reminder
  - Emit a PyQt6 signal when the reminder threshold is crossed
  - Track break history (took break / skipped)

Architecture:
  ActivityMonitor (QObject) — lives on the main thread, owns the QTimer
  _InputListener              — thin wrapper around pynput, runs in its own
                                daemon thread; communicates back via a
                                thread-safe callback
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from src.utils.logger import get_logger
from src.core.constants import (
    ACTIVITY_POLL_INTERVAL_MS,
    DEFAULT_REMINDER_INTERVAL_MINUTES,
    DEFAULT_IDLE_RESET_MINUTES,
    DEFAULT_SNOOZE_MINUTES,
)

log = get_logger(__name__)


# ── Session state snapshot ────────────────────────────────────────────────────

@dataclass
class SessionState:
    """Immutable snapshot of the current session — safe to read from any thread."""
    active_seconds: float = 0.0
    idle_seconds: float = 0.0
    is_idle: bool = False
    reminder_interval_seconds: float = DEFAULT_REMINDER_INTERVAL_MINUTES * 60
    breaks_taken: int = 0
    breaks_skipped: int = 0
    total_session_seconds: float = 0.0


# ── pynput listener wrapper ───────────────────────────────────────────────────

class _InputListener:
    """
    Wraps pynput keyboard + mouse listeners.
    Calls `on_activity()` whenever any input event is detected.
    Runs in daemon threads — stops automatically when the main process exits.
    """

    def __init__(self, on_activity: Callable[[], None]) -> None:
        self._on_activity = on_activity
        self._kb_listener = None
        self._ms_listener = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        try:
            from pynput import keyboard, mouse

            self._kb_listener = keyboard.Listener(
                on_press=self._handle_event,
                daemon=True,
            )
            self._ms_listener = mouse.Listener(
                on_move=self._handle_event,
                on_click=self._handle_event,
                on_scroll=self._handle_event,
                daemon=True,
            )
            self._kb_listener.start()
            self._ms_listener.start()
            self._running = True
            log.info("Input listeners started (keyboard + mouse).")
        except Exception as exc:
            log.error("Failed to start input listeners: %s", exc)
            log.warning("Activity monitoring will run in timer-only mode.")

    def stop(self) -> None:
        if not self._running:
            return
        try:
            if self._kb_listener:
                self._kb_listener.stop()
            if self._ms_listener:
                self._ms_listener.stop()
        except Exception as exc:
            log.warning("Error stopping input listeners: %s", exc)
        finally:
            self._running = False
            log.info("Input listeners stopped.")

    def _handle_event(self, *_args) -> None:
        """Called from pynput's thread — just forward to the callback."""
        try:
            self._on_activity()
        except Exception:
            pass  # never crash the listener thread


# ── Main activity monitor ─────────────────────────────────────────────────────

class ActivityMonitor(QObject):
    """
    The central activity monitoring engine.

    Signals:
        reminder_triggered  — emitted when active time >= threshold
        session_updated     — emitted every tick with the latest SessionState
        idle_started        — emitted when the user goes idle
        idle_ended          — emitted when the user returns from idle

    Usage:
        monitor = ActivityMonitor(config)
        monitor.reminder_triggered.connect(my_popup_slot)
        monitor.start()
    """

    reminder_triggered = pyqtSignal(object)   # payload: SessionState
    session_updated    = pyqtSignal(object)   # payload: SessionState
    idle_started       = pyqtSignal()
    idle_ended         = pyqtSignal()

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        # ── Config ────────────────────────────────────────────────────────────
        reminder_cfg = config.get("reminder", {})
        self._reminder_interval_s: float = (
            reminder_cfg.get("interval_minutes", DEFAULT_REMINDER_INTERVAL_MINUTES) * 60
        )
        self._idle_reset_s: float = (
            reminder_cfg.get("idle_reset_minutes", DEFAULT_IDLE_RESET_MINUTES) * 60
        )
        self._snooze_s: float = (
            reminder_cfg.get("snooze_minutes", DEFAULT_SNOOZE_MINUTES) * 60
        )
        self._enabled: bool = reminder_cfg.get("enabled", True)

        # ── Internal state (protected by _lock) ───────────────────────────────
        self._lock = threading.Lock()
        self._last_activity_time: float = time.monotonic()
        self._active_seconds: float = 0.0
        self._total_seconds: float = 0.0
        self._is_idle: bool = False
        self._reminder_fired: bool = False   # prevents double-firing per session
        self._snooze_until: float = 0.0      # monotonic timestamp; 0 = not snoozing
        self._breaks_taken: int = 0
        self._breaks_skipped: int = 0

        # ── Tick timer (runs on main Qt thread) ───────────────────────────────
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(ACTIVITY_POLL_INTERVAL_MS)
        self._tick_timer.timeout.connect(self._tick)

        # ── pynput listener ───────────────────────────────────────────────────
        self._listener = _InputListener(on_activity=self._on_input_activity)

        log.info(
            "ActivityMonitor created — interval: %.0f min, idle reset: %.0f min",
            self._reminder_interval_s / 60,
            self._idle_reset_s / 60,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start monitoring. Safe to call multiple times."""
        if not self._enabled:
            log.info("ActivityMonitor is disabled in config — not starting.")
            return
        self._listener.start()
        self._tick_timer.start()
        log.info("ActivityMonitor started.")

    def stop(self) -> None:
        """Stop monitoring and release resources."""
        self._tick_timer.stop()
        self._listener.stop()
        log.info("ActivityMonitor stopped.")

    def record_break_taken(self) -> None:
        """Call when the user clicks 'OK, I'll take a break'."""
        with self._lock:
            self._breaks_taken += 1
            self._reset_session()
        log.info("Break taken. Session reset. Total breaks taken: %d", self._breaks_taken)

    def record_break_skipped(self) -> None:
        """Call when the user clicks 'Skip for now'. Snoozes for snooze_minutes."""
        with self._lock:
            self._breaks_skipped += 1
            self._snooze_until = time.monotonic() + self._snooze_s
            self._reminder_fired = False   # allow re-firing after snooze
        log.info(
            "Break skipped. Snoozing for %.0f min. Total skips: %d",
            self._snooze_s / 60,
            self._breaks_skipped,
        )

    def get_state(self) -> SessionState:
        """Thread-safe snapshot of the current session state."""
        with self._lock:
            return SessionState(
                active_seconds=self._active_seconds,
                idle_seconds=max(0.0, time.monotonic() - self._last_activity_time)
                             if self._is_idle else 0.0,
                is_idle=self._is_idle,
                reminder_interval_seconds=self._reminder_interval_s,
                breaks_taken=self._breaks_taken,
                breaks_skipped=self._breaks_skipped,
                total_session_seconds=self._total_seconds,
            )

    def update_interval(self, minutes: int) -> None:
        """Hot-update the reminder interval (called from Settings)."""
        with self._lock:
            self._reminder_interval_s = minutes * 60
        log.info("Reminder interval updated to %d min.", minutes)

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable monitoring at runtime."""
        self._enabled = enabled
        if enabled:
            self.start()
        else:
            self.stop()
        log.info("ActivityMonitor enabled=%s", enabled)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _on_input_activity(self) -> None:
        """Called from pynput's thread on any keyboard/mouse event."""
        with self._lock:
            self._last_activity_time = time.monotonic()

    def _tick(self) -> None:
        """
        Called every ACTIVITY_POLL_INTERVAL_MS on the main Qt thread.
        Advances the session timer and checks all thresholds.
        """
        now = time.monotonic()
        tick_s = ACTIVITY_POLL_INTERVAL_MS / 1000.0

        with self._lock:
            idle_s = now - self._last_activity_time
            was_idle = self._is_idle

            # ── Idle detection ────────────────────────────────────────────────
            if idle_s >= self._idle_reset_s:
                if not was_idle:
                    self._is_idle = True
                    log.debug(
                        "User went idle after %.0f s — session timer paused.", idle_s
                    )
                # While idle, do not accumulate active time
                state = self._build_state(idle_s)

            else:
                if was_idle:
                    # Returning from idle
                    self._is_idle = False
                    self._active_seconds = 0.0   # fresh session after idle break
                    log.debug("User returned from idle — session timer reset.")

                self._active_seconds += tick_s
                self._total_seconds  += tick_s
                state = self._build_state(0.0)

            should_fire = (
                not self._is_idle
                and not self._reminder_fired
                and self._active_seconds >= self._reminder_interval_s
                and now >= self._snooze_until
            )

        # ── Emit signals (outside lock) ───────────────────────────────────────
        if was_idle and not state.is_idle:
            self.idle_ended.emit()
        elif not was_idle and state.is_idle:
            self.idle_started.emit()

        self.session_updated.emit(state)

        if should_fire:
            with self._lock:
                self._reminder_fired = True
            log.info(
                "Reminder triggered — active for %.1f min.",
                state.active_seconds / 60,
            )
            self.reminder_triggered.emit(state)

    def _build_state(self, idle_s: float) -> SessionState:
        """Build a SessionState from current locked values. Must hold _lock."""
        return SessionState(
            active_seconds=self._active_seconds,
            idle_seconds=idle_s,
            is_idle=self._is_idle,
            reminder_interval_seconds=self._reminder_interval_s,
            breaks_taken=self._breaks_taken,
            breaks_skipped=self._breaks_skipped,
            total_session_seconds=self._total_seconds,
        )

    def _reset_session(self) -> None:
        """Reset the active session counter. Must hold _lock."""
        self._active_seconds = 0.0
        self._reminder_fired = False
        self._snooze_until = 0.0
        self._is_idle = False
        self._last_activity_time = time.monotonic()
