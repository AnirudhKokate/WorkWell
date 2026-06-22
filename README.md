# WorkWell — Developer Documentation

> Cross-platform desktop health reminder app  
> Python 3.11+ · PyQt6 · pynput · SQLite

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [File Structure](#2-file-structure)
3. [Setup & Running](#3-setup--running)
4. [Architecture](#4-architecture)
5. [Configuration](#5-configuration)
6. [Running Tests](#6-running-tests)
7. [Performance Targets](#7-performance-targets)
8. [Building a Binary (PyInstaller)](#8-building-a-binary-pyinstaller)
9. [Cross-Platform Notes](#9-cross-platform-notes)
10. [Phase Roadmap](#10-phase-roadmap)

---

## 1. Project Overview

WorkWell monitors keyboard and mouse activity and triggers a full-screen health reminder after a configurable period of continuous computer use (default 35 minutes). It runs silently in the system tray and stores session data locally in SQLite.

**Personal use only.** No public distribution, no telemetry, no network calls (unless the AI assistant is enabled).

---

## 2. File Structure

```
WorkWell/
├── main.py                     # App entry point
├── workwell.spec               # PyInstaller build spec
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── config/
│   └── defaults.json           # Shipped default configuration
├── assets/
│   └── icons/
│       ├── tray.png            # Active tray icon (32×32)
│       └── tray_paused.png     # Paused tray icon (32×32)
├── src/
│   ├── core/
│   │   ├── activity_monitor.py # Keyboard/mouse listener + session timer
│   │   ├── constants.py        # App-wide constants and health content
│   │   └── health_content.py   # Rotating facts + tips (extended set)
│   ├── db/
│   │   └── session_log.py      # SQLite session event logger
│   ├── ui/
│   │   ├── reminder_popup.py   # Full-screen reminder modal (Phase 4)
│   │   ├── settings_window.py  # Settings dialog (Phase 6)
│   │   └── tray_manager.py     # System tray icon + context menu
│   └── utils/
│       ├── logger.py           # Rotating file logger setup
│       ├── paths.py            # Platform-aware directory resolution
│       ├── perf_monitor.py     # CPU/RAM sampler (Phase 7)
│       └── startup.py          # OS startup registration
└── tests/
    ├── test_phase1.py
    ├── test_phase2.py
    ├── test_phase3.py
    ├── test_phase4.py
    ├── test_phase6.py
    └── test_phase7.py
```

---

## 3. Setup & Running

### Prerequisites

- Python 3.11 or newer
- A desktop environment with a system tray (GNOME, KDE, XFCE, Windows shell)

### Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

### Run

```bash
python main.py
```

WorkWell starts silently in the system tray. Right-click the tray icon for the context menu.

---

## 4. Architecture

```
main.py
  │
  ├── ActivityMonitor          (QThread — polls pynput every 1 s)
  │     signals: reminder_triggered(SessionState)
  │              session_updated(SessionState)
  │
  ├── ReminderPopup            (QWidget — shown on reminder_triggered)
  │     signals: break_taken / skipped
  │
  ├── TrayManager              (QSystemTrayIcon)
  │     signals: quit_requested / pause_toggled / settings_requested
  │
  ├── SettingsWindow           (QDialog — opened via tray)
  │     signals: settings_saved(dict)
  │
  ├── SessionLogger            (SQLite — thread-safe, append-only)
  │
  └── PerfMonitor              (daemon thread — samples CPU/RAM every 10 s)
```

**Signal flow for a reminder cycle:**

```
ActivityMonitor.reminder_triggered
  → ReminderPopup.show_popup()
  → SessionLogger.log_reminder_shown()
  → user clicks "Take break"
      → ReminderPopup.break_taken
      → ActivityMonitor.record_break_taken()
      → SessionLogger.log_break_taken()
```

---

## 5. Configuration

User config is stored at:

| Platform | Path |
|----------|------|
| Linux    | `~/.local/share/WorkWell/config.json` |
| Windows  | `%APPDATA%\WorkWell\config.json` |
| macOS    | `~/Library/Application Support/WorkWell/config.json` |

On first run, `config/defaults.json` is merged into the user config. All keys and their defaults:

```json
{
  "reminder": {
    "interval_minutes": 35,
    "enabled": true,
    "idle_reset_minutes": 5,
    "snooze_minutes": 15
  },
  "startup": {
    "launch_on_boot": true,
    "minimize_to_tray": true
  },
  "appearance": {
    "theme": "dark",
    "popup_opacity": 0.92
  },
  "ai_assistant": {
    "enabled": false,
    "provider": "openai",
    "api_key": "",
    "model": "gpt-4o-mini"
  },
  "logging": {
    "enabled": true,
    "log_level": "INFO",
    "log_responses": true
  }
}
```

Settings changed via the UI are written atomically (temp-file + rename) so a crash mid-save never corrupts the config.

---

## 6. Running Tests

```bash
# All phases
python -m pytest tests/ -v

# Single phase
python -m pytest tests/test_phase7.py -v

# With coverage (requires pytest-cov)
pip install pytest-cov
python -m pytest tests/ --cov=src --cov-report=term-missing
```

---

## 7. Performance Targets

WorkWell is a background utility. At idle it must not noticeably impact system performance:

| Metric | Target |
|--------|--------|
| CPU (idle, 1-core %) | < 1 % |
| RAM (RSS) | < 80 MB |
| Startup time | < 3 s |
| Reminder popup render | < 300 ms |

`PerfMonitor` logs a warning if CPU exceeds 5 % or RAM exceeds 150 MB. Check `~/.local/share/WorkWell/logs/workwell.log` for warnings.

---

## 8. Building a Binary (PyInstaller)

```bash
pip install pyinstaller

# One-folder build (recommended for first-time testing)
pyinstaller workwell.spec

# Output is in dist/WorkWell/
# Run with:
./dist/WorkWell/WorkWell          # Linux
dist\WorkWell\WorkWell.exe        # Windows
```

**Single-file build:** set `onefile = True` in `workwell.spec`, then re-run `pyinstaller workwell.spec`. Startup is slower but distribution is a single file.

**Linux note:** Build on the oldest glibc version you need to support (e.g. Ubuntu 20.04) for maximum compatibility.

**Windows note:** If you need a `.ico` file for the Windows taskbar/tray, convert `assets/icons/tray.png` with:
```bash
pip install pillow
python -c "from PIL import Image; Image.open('assets/icons/tray.png').save('assets/icons/tray.ico')"
```
Then update `ICON_WIN` in `workwell.spec` to point to the `.ico` file.

---

## 9. Cross-Platform Notes

### Linux

- System tray requires `libappindicator` or a compatible tray host (GNOME needs the [AppIndicator extension](https://extensions.gnome.org/extension/615/appindicator-support/)).
- Startup registration writes a `.desktop` file to `~/.config/autostart/`.
- `pynput` on Linux uses X11 by default; Wayland support is limited.

### Windows

- Startup registration writes to `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
- No additional dependencies needed for the tray.
- Run from a standard user account; no elevation required.

---

## 10. Phase Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ Done | Project setup, logging, config, app skeleton |
| 2 | ✅ Done | Activity monitor (pynput, idle detection, session timer) |
| 3 | ✅ Done | System tray, background daemon, startup-on-boot |
| 4 | ✅ Done | Full-screen reminder popup, health facts, tips sidebar |
| 5 | ⏭ Skipped | AI health assistant chatbot (Phase 5 deferred) |
| 6 | ✅ Done | Settings window, config persistence, SQLite session logging |
| 7 | ✅ Done | Polish, performance audit, PyInstaller spec, documentation |
