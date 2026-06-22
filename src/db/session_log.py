"""
workwell/src/db/session_log.py

SQLite-backed session logger for Phase 6.

Records every reminder event (break taken / skipped / dismissed) with
timestamps, active-minutes, and the response the user chose.  The table
is append-only; nothing is ever deleted — the data is intended for future
analytics (streak tracking, skip-rate graphs, etc.).

Schema
------
session_events
  id             INTEGER PRIMARY KEY AUTOINCREMENT
  ts             TEXT     NOT NULL   -- ISO-8601 UTC timestamp
  event          TEXT     NOT NULL   -- 'break_taken' | 'skipped' | 'reminder_shown'
  active_minutes INTEGER  NOT NULL   -- how many active minutes triggered this
  note           TEXT                -- optional free-form context

Public API
----------
  logger = SessionLogger(db_path)
  logger.log_reminder_shown(active_minutes)
  logger.log_break_taken(active_minutes)
  logger.log_skipped(active_minutes)
  rows   = logger.get_recent(limit=50)
  stats  = logger.get_summary()        # dict with totals and rate
  logger.close()                       # explicit close (also called on __del__)
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

# ── Event constants (use these everywhere; never bare strings) ────────────────
EVENT_REMINDER_SHOWN = "reminder_shown"
EVENT_BREAK_TAKEN    = "break_taken"
EVENT_SKIPPED        = "skipped"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS session_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT    NOT NULL,
    event          TEXT    NOT NULL,
    active_minutes INTEGER NOT NULL DEFAULT 0,
    note           TEXT
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_session_events_ts
    ON session_events (ts);
"""


class SessionLogger:
    """Thread-safe SQLite session logger.

    A single write-lock (threading.Lock) serialises all INSERT calls so the
    logger can be safely called from Qt main-thread signals without an extra
    layer of queueing.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._connect()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def _connect(self) -> None:
        """Open (or create) the SQLite database and ensure the schema exists."""
        try:
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,   # we guard with self._lock
                isolation_level=None,      # autocommit — each INSERT is atomic
            )
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute(_CREATE_TABLE_SQL)
            self._conn.execute(_CREATE_INDEX_SQL)
            log.info("SessionLogger: database ready at %s", self._db_path)
        except sqlite3.Error as exc:
            log.error("SessionLogger: failed to open database — %s", exc)
            self._conn = None

    def close(self) -> None:
        """Explicitly close the database connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            finally:
                self._conn = None

    def __del__(self) -> None:
        self.close()

    # ── Public logging methods ─────────────────────────────────────────────────

    def log_reminder_shown(self, active_minutes: int, note: str = "") -> None:
        """Called when the reminder popup is displayed."""
        self._insert(EVENT_REMINDER_SHOWN, active_minutes, note)

    def log_break_taken(self, active_minutes: int, note: str = "") -> None:
        """Called when the user clicks 'OK, I'll take a break'."""
        self._insert(EVENT_BREAK_TAKEN, active_minutes, note)

    def log_skipped(self, active_minutes: int, note: str = "") -> None:
        """Called when the user clicks 'Skip'."""
        self._insert(EVENT_SKIPPED, active_minutes, note)

    # ── Querying ──────────────────────────────────────────────────────────────

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the *limit* most-recent events, newest first."""
        if self._conn is None:
            return []
        try:
            with self._lock:
                cur = self._conn.execute(
                    "SELECT id, ts, event, active_minutes, note "
                    "FROM session_events ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except sqlite3.Error as exc:
            log.error("SessionLogger.get_recent error: %s", exc)
            return []

    def get_summary(self) -> dict[str, Any]:
        """Return aggregate statistics across all recorded events.

        Returns
        -------
        dict with keys:
          total_reminders  int
          total_breaks     int
          total_skips      int
          break_rate       float   (0.0 – 1.0); 0.0 if no reminders responded to
          first_event_ts   str | None
          last_event_ts    str | None
        """
        if self._conn is None:
            return _empty_summary()
        try:
            with self._lock:
                cur = self._conn.execute(
                    """
                    SELECT
                        SUM(event = 'reminder_shown') AS shown,
                        SUM(event = 'break_taken')    AS breaks,
                        SUM(event = 'skipped')        AS skips,
                        MIN(ts)                       AS first_ts,
                        MAX(ts)                       AS last_ts
                    FROM session_events
                    """
                )
                row = cur.fetchone()
        except sqlite3.Error as exc:
            log.error("SessionLogger.get_summary error: %s", exc)
            return _empty_summary()

        shown  = row[0] or 0
        breaks = row[1] or 0
        skips  = row[2] or 0
        responded = breaks + skips
        return {
            "total_reminders": shown,
            "total_breaks":    breaks,
            "total_skips":     skips,
            "break_rate":      (breaks / responded) if responded > 0 else 0.0,
            "first_event_ts":  row[3],
            "last_event_ts":   row[4],
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _insert(self, event: str, active_minutes: int, note: str) -> None:
        if self._conn is None:
            log.warning("SessionLogger: no database connection; skipping log.")
            return
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO session_events (ts, event, active_minutes, note) "
                    "VALUES (?, ?, ?, ?)",
                    (ts, event, int(active_minutes), note or None),
                )
            log.debug("SessionLogger: %s  active=%d min", event, active_minutes)
        except sqlite3.Error as exc:
            log.error("SessionLogger._insert error: %s", exc)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _empty_summary() -> dict[str, Any]:
    return {
        "total_reminders": 0,
        "total_breaks":    0,
        "total_skips":     0,
        "break_rate":      0.0,
        "first_event_ts":  None,
        "last_event_ts":   None,
    }
