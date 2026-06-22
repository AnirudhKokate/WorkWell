"""
workwell/tests/test_phase2.py

Phase 2 tests — Activity Monitoring Engine.
Run with:  python -m pytest tests/test_phase2.py -v
"""

import sys
import time
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from src.core.activity_monitor import ActivityMonitor, SessionState, _InputListener
from src.core.constants import (
    DEFAULT_REMINDER_INTERVAL_MINUTES,
    DEFAULT_IDLE_RESET_MINUTES,
    DEFAULT_SNOOZE_MINUTES,
    ACTIVITY_POLL_INTERVAL_MS,
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
            "interval_minutes": DEFAULT_REMINDER_INTERVAL_MINUTES,
            "idle_reset_minutes": DEFAULT_IDLE_RESET_MINUTES,
            "snooze_minutes": DEFAULT_SNOOZE_MINUTES,
            "enabled": True,
        },
        "logging": {"log_level": "DEBUG"},
    }


@pytest.fixture
def fast_config():
    """Config with very short intervals for fast testing."""
    return {
        "reminder": {
            "interval_minutes": 0.05,   # 3 seconds
            "idle_reset_minutes": 0.1,  # 6 seconds
            "snooze_minutes": 0.05,     # 3 seconds
            "enabled": True,
        },
        "logging": {"log_level": "DEBUG"},
    }


# ── SessionState dataclass ────────────────────────────────────────────────────

def test_session_state_defaults():
    s = SessionState()
    assert s.active_seconds == 0.0
    assert s.idle_seconds == 0.0
    assert s.is_idle is False
    assert s.breaks_taken == 0
    assert s.breaks_skipped == 0
    assert s.total_session_seconds == 0.0


def test_session_state_custom_values():
    s = SessionState(active_seconds=120.0, breaks_taken=2, is_idle=True)
    assert s.active_seconds == 120.0
    assert s.breaks_taken == 2
    assert s.is_idle is True


# ── ActivityMonitor construction ──────────────────────────────────────────────

def test_monitor_creates_without_error(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    assert monitor is not None


def test_monitor_reads_interval_from_config(qt_app, base_config):
    base_config["reminder"]["interval_minutes"] = 42
    monitor = ActivityMonitor(base_config)
    assert monitor._reminder_interval_s == 42 * 60


def test_monitor_reads_idle_reset_from_config(qt_app, base_config):
    base_config["reminder"]["idle_reset_minutes"] = 10
    monitor = ActivityMonitor(base_config)
    assert monitor._idle_reset_s == 10 * 60


def test_monitor_reads_snooze_from_config(qt_app, base_config):
    base_config["reminder"]["snooze_minutes"] = 20
    monitor = ActivityMonitor(base_config)
    assert monitor._snooze_s == 20 * 60


def test_monitor_disabled_config(qt_app, base_config):
    base_config["reminder"]["enabled"] = False
    monitor = ActivityMonitor(base_config)
    assert monitor._enabled is False


# ── get_state ─────────────────────────────────────────────────────────────────

def test_get_state_returns_session_state(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    state = monitor.get_state()
    assert isinstance(state, SessionState)


def test_get_state_initial_active_zero(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    state = monitor.get_state()
    assert state.active_seconds == 0.0


def test_get_state_is_not_idle_initially(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    state = monitor.get_state()
    assert state.is_idle is False


# ── record_break_taken ────────────────────────────────────────────────────────

def test_record_break_taken_increments_counter(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    monitor.record_break_taken()
    assert monitor._breaks_taken == 1
    monitor.record_break_taken()
    assert monitor._breaks_taken == 2


def test_record_break_taken_resets_active_seconds(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    with monitor._lock:
        monitor._active_seconds = 999.0
    monitor.record_break_taken()
    with monitor._lock:
        assert monitor._active_seconds == 0.0


def test_record_break_taken_clears_reminder_fired(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    with monitor._lock:
        monitor._reminder_fired = True
    monitor.record_break_taken()
    with monitor._lock:
        assert monitor._reminder_fired is False


# ── record_break_skipped ──────────────────────────────────────────────────────

def test_record_break_skipped_increments_counter(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    monitor.record_break_skipped()
    assert monitor._breaks_skipped == 1


def test_record_break_skipped_sets_snooze(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    before = time.monotonic()
    monitor.record_break_skipped()
    after = time.monotonic()
    with monitor._lock:
        assert monitor._snooze_until > before
        assert monitor._snooze_until <= after + monitor._snooze_s + 0.1


def test_record_break_skipped_clears_reminder_fired(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    with monitor._lock:
        monitor._reminder_fired = True
    monitor.record_break_skipped()
    with monitor._lock:
        assert monitor._reminder_fired is False


# ── update_interval ───────────────────────────────────────────────────────────

def test_update_interval_changes_reminder_seconds(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    monitor.update_interval(60)
    with monitor._lock:
        assert monitor._reminder_interval_s == 60 * 60


def test_update_interval_accepts_minimum_value(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    monitor.update_interval(1)
    with monitor._lock:
        assert monitor._reminder_interval_s == 60


# ── _on_input_activity ────────────────────────────────────────────────────────

def test_input_activity_updates_last_activity_time(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    old_time = monitor._last_activity_time
    time.sleep(0.05)
    monitor._on_input_activity()
    assert monitor._last_activity_time > old_time


# ── _tick: active accumulation ────────────────────────────────────────────────

def test_tick_accumulates_active_seconds(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    # Ensure not idle
    monitor._on_input_activity()
    before = monitor._active_seconds
    monitor._tick()
    after = monitor._active_seconds
    assert after > before


def test_tick_does_not_accumulate_when_idle(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    with monitor._lock:
        monitor._is_idle = True
        monitor._last_activity_time = time.monotonic() - monitor._idle_reset_s - 1
        before = monitor._active_seconds
    monitor._tick()
    with monitor._lock:
        assert monitor._active_seconds == before


# ── _tick: idle detection ─────────────────────────────────────────────────────

def test_tick_detects_idle(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    # Force last activity to be longer ago than the idle threshold
    with monitor._lock:
        monitor._last_activity_time = time.monotonic() - monitor._idle_reset_s - 1
    monitor._tick()
    with monitor._lock:
        assert monitor._is_idle is True


def test_tick_exits_idle_on_activity(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    with monitor._lock:
        monitor._is_idle = True
        monitor._last_activity_time = time.monotonic()   # fresh activity
    monitor._tick()
    with monitor._lock:
        assert monitor._is_idle is False


# ── _tick: reminder firing ────────────────────────────────────────────────────

def test_tick_fires_reminder_when_threshold_crossed(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    fired = []
    monitor.reminder_triggered.connect(lambda s: fired.append(s))

    # Manually push active time past threshold
    with monitor._lock:
        monitor._active_seconds = monitor._reminder_interval_s + 1
        monitor._last_activity_time = time.monotonic()

    monitor._tick()
    assert len(fired) == 1
    assert isinstance(fired[0], SessionState)


def test_tick_does_not_double_fire_reminder(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    fired = []
    monitor.reminder_triggered.connect(lambda s: fired.append(s))

    with monitor._lock:
        monitor._active_seconds = monitor._reminder_interval_s + 1
        monitor._last_activity_time = time.monotonic()

    monitor._tick()
    monitor._tick()
    assert len(fired) == 1   # only once


def test_tick_does_not_fire_during_snooze(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    fired = []
    monitor.reminder_triggered.connect(lambda s: fired.append(s))

    with monitor._lock:
        monitor._active_seconds = monitor._reminder_interval_s + 1
        monitor._snooze_until = time.monotonic() + 9999   # far future
        monitor._last_activity_time = time.monotonic()

    monitor._tick()
    assert len(fired) == 0


def test_tick_fires_after_snooze_expires(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    fired = []
    monitor.reminder_triggered.connect(lambda s: fired.append(s))

    with monitor._lock:
        monitor._active_seconds = monitor._reminder_interval_s + 1
        monitor._snooze_until = time.monotonic() - 1   # already expired
        monitor._reminder_fired = False
        monitor._last_activity_time = time.monotonic()

    monitor._tick()
    assert len(fired) == 1


# ── Signals ───────────────────────────────────────────────────────────────────

def test_session_updated_signal_emits_on_tick(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    updates = []
    monitor.session_updated.connect(lambda s: updates.append(s))
    monitor._on_input_activity()
    monitor._tick()
    assert len(updates) == 1
    assert isinstance(updates[0], SessionState)


def test_idle_started_signal_emits(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    signals = []
    monitor.idle_started.connect(lambda: signals.append(True))

    with monitor._lock:
        monitor._last_activity_time = time.monotonic() - monitor._idle_reset_s - 1

    monitor._tick()
    assert len(signals) == 1


def test_idle_ended_signal_emits(qt_app, base_config):
    monitor = ActivityMonitor(base_config)
    signals = []
    monitor.idle_ended.connect(lambda: signals.append(True))

    # Start as idle
    with monitor._lock:
        monitor._is_idle = True
        monitor._last_activity_time = time.monotonic()   # activity just happened

    monitor._tick()
    assert len(signals) == 1


# ── _InputListener ────────────────────────────────────────────────────────────

def test_input_listener_calls_callback(qt_app):
    called = []
    listener = _InputListener(on_activity=lambda: called.append(True))
    listener._handle_event()
    assert len(called) == 1


def test_input_listener_handles_callback_exception(qt_app):
    """Listener must never crash even if callback raises."""
    def bad_callback():
        raise RuntimeError("boom")

    listener = _InputListener(on_activity=bad_callback)
    listener._handle_event()   # should not raise


def test_input_listener_stop_when_not_started(qt_app):
    """Stopping a never-started listener must not raise."""
    listener = _InputListener(on_activity=lambda: None)
    listener.stop()   # should not raise
