"""
workwell/src/utils/logger.py

Centralized logging for WorkWell.
Call setup_logging() once at startup; everywhere else just do:

    from workwell.src.utils.logger import get_logger
    log = get_logger(__name__)
    log.info("Something happened")
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional


_initialized = False


def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    """
    Configure root logger with:
      - Rotating file handler  (logs/workwell.log, 5 MB × 3 backups)
      - Console handler        (stdout, same level)

    Safe to call multiple times — second call is a no-op.
    """
    global _initialized
    if _initialized:
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "workwell.log"

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    root.addHandler(console_handler)

    _initialized = True

    root.info("WorkWell logging initialised — log file: %s", log_file)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a named logger. Call after setup_logging()."""
    return logging.getLogger(name or "workwell")
