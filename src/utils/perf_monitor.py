"""
workwell/src/utils/perf_monitor.py

Lightweight CPU / RAM performance monitor for Phase 7.

Samples the current process's CPU and RSS memory usage on a background
thread and exposes the latest readings via thread-safe properties.
Optionally emits a Qt signal when usage exceeds configurable thresholds.

Usage (standalone, no Qt required):
    mon = PerfMonitor(interval_secs=5)
    mon.start()
    time.sleep(30)
    print(mon.latest)   # {'cpu_pct': 0.3, 'rss_mb': 42.1}
    mon.stop()

Usage (with Qt signal):
    mon = PerfMonitor(interval_secs=5)
    mon.stats_updated.connect(lambda s: print(s))
    mon.start()
"""

from __future__ import annotations

import threading
import time
from typing import Any

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

from src.utils.logger import get_logger

log = get_logger(__name__)

# Thresholds that trigger a warning log
_CPU_WARN_PCT  = 5.0    # % of one core — WorkWell should never hit this
_RAM_WARN_MB   = 150.0  # MB RSS — generous ceiling for a tray app


class PerfMonitor:
    """Background performance sampler.

    Thread-safe: start/stop from any thread; read .latest from any thread.
    Does not require PyQt6 — works as a plain Python utility.
    """

    def __init__(self, interval_secs: float = 10.0) -> None:
        self._interval = interval_secs
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest: dict[str, Any] = {"cpu_pct": 0.0, "rss_mb": 0.0}

        if not _PSUTIL_AVAILABLE:
            log.warning(
                "psutil not installed — PerfMonitor will return zeros. "
                "Install it with: pip install psutil"
            )
        else:
            self._proc = psutil.Process()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def latest(self) -> dict[str, Any]:
        """Return the most-recent sample as {'cpu_pct': float, 'rss_mb': float}."""
        with self._lock:
            return dict(self._latest)

    def start(self) -> None:
        """Start the background sampling thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="PerfMonitor", daemon=True
        )
        self._thread.start()
        log.debug("PerfMonitor started (interval=%ss).", self._interval)

    def stop(self) -> None:
        """Stop the background thread (blocks until it exits)."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._interval + 1)
        log.debug("PerfMonitor stopped.")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _sample(self) -> dict[str, Any]:
        if not _PSUTIL_AVAILABLE:
            return {"cpu_pct": 0.0, "rss_mb": 0.0}
        try:
            cpu = self._proc.cpu_percent(interval=None)
            rss = self._proc.memory_info().rss / (1024 * 1024)
            return {"cpu_pct": round(cpu, 2), "rss_mb": round(rss, 1)}
        except psutil.Error as exc:
            log.warning("PerfMonitor sample error: %s", exc)
            return {"cpu_pct": 0.0, "rss_mb": 0.0}

    def _run(self) -> None:
        # Warm-up call so the first real reading isn't 0 %
        if _PSUTIL_AVAILABLE:
            try:
                self._proc.cpu_percent(interval=None)
            except psutil.Error:
                pass

        while not self._stop_event.wait(self._interval):
            sample = self._sample()
            with self._lock:
                self._latest = sample

            if sample["cpu_pct"] > _CPU_WARN_PCT:
                log.warning(
                    "PerfMonitor: high CPU usage — %.1f %%", sample["cpu_pct"]
                )
            if sample["rss_mb"] > _RAM_WARN_MB:
                log.warning(
                    "PerfMonitor: high RAM usage — %.1f MB", sample["rss_mb"]
                )
