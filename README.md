# WorkWell

A cross-platform desktop health reminder that monitors keyboard and mouse activity and triggers a full-screen break reminder after a configurable period of continuous computer use.

Runs silently in the system tray. No telemetry. No network calls (unless the AI assistant is enabled).

---

## Requirements

- Python 3.11 or newer
- A desktop environment with a system tray (GNOME, KDE, XFCE, Windows shell)

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows

pip install -r requirements.txt
python main.py
```

WorkWell starts in the system tray. Right-click the icon for options.

---

## What it does

- Tracks active time via keyboard and mouse input using `pynput`
- Detects idle periods and pauses the session timer automatically
- After the configured interval (default 35 minutes), shows a full-screen reminder popup
- The popup covers ~75% of the screen with a dimmed background, rotating health facts, a scrollable tips sidebar, and two action buttons
- "OK, I'll take a break" resets the session timer; "Skip for now" snoozes for a configurable duration
- All session events (reminders shown, breaks taken, skips) are logged locally to SQLite for future analytics
- Settings are persisted to a local JSON config file

---

## Configuration

Config is stored at:

| Platform | Path |
|----------|------|
| Linux    | `~/.local/share/WorkWell/config.json` |
| Windows  | `%APPDATA%\WorkWell\config.json` |

Key settings (all adjustable in the Settings window):

| Setting | Default |
|---------|---------|
| Reminder interval | 35 min |
| Idle reset threshold | 5 min |
| Snooze duration | 15 min |
| Theme | dark |
| Launch on boot | enabled |
| Session logging | enabled |

---

## Supported platforms

- Windows
- Linux

---

## File structure

```
WorkWell/
├── main.py                     # Entry point
├── requirements.txt
├── workwell.spec               # PyInstaller build spec
├── config/
│   └── defaults.json
├── assets/
│   └── icons/
│       ├── tray.png
│       └── tray_paused.png
├── src/
│   ├── core/
│   │   ├── activity_monitor.py
│   │   ├── constants.py
│   │   └── health_content.py
│   ├── db/
│   │   └── session_log.py
│   ├── ui/
│   │   ├── reminder_popup.py
│   │   ├── settings_window.py
│   │   └── tray_manager.py
│   └── utils/
│       ├── logger.py
│       ├── paths.py
│       ├── perf_monitor.py
│       └── startup.py
└── tests/
    ├── test_phase1.py
    ├── test_phase2.py
    ├── test_phase3.py
    ├── test_phase4.py
    ├── test_phase6.py
    └── test_phase7.py
```

---

## Running tests

```bash
python -m pytest tests/ -v
```

---

## Building a binary

```bash
pip install pyinstaller
pyinstaller workwell.spec
# Output: dist/WorkWell/
```

Set `onefile = True` in `workwell.spec` for a single-file build.

**Linux note:** Build on the oldest glibc version you need to support (e.g. Ubuntu 20.04).

**Windows note:** Convert `assets/icons/tray.png` to `.ico` and update `ICON_WIN` in the spec if you want a proper taskbar icon.

---

## Startup registration

WorkWell registers itself to launch on boot automatically if `launch_on_boot` is enabled in config.

- **Linux:** writes a `.desktop` file and shell wrapper to `~/.config/autostart/`
- **Windows:** writes a value to `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`

---

## Phase status

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ Done | Project setup, logging, config, app skeleton |
| 2 | ✅ Done | Activity monitor — pynput, idle detection, session timer |
| 3 | ✅ Done | System tray, background daemon, startup-on-boot |
| 4 | ✅ Done | Full-screen reminder popup, health facts, tips sidebar |
| 5 | ⏭ Skipped | AI health assistant chatbot (deferred) |
| 6 | ✅ Done | Settings window, config persistence, SQLite session logging |
| 7 | ✅ Done | Performance monitor, PyInstaller spec, cross-platform QA |
