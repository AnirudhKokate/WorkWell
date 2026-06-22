"""
workwell/src/utils/startup.py

Cross-platform startup-on-boot integration for WorkWell.

Windows:
  Writes / removes a registry value under
  HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
  pointing to the Python interpreter + main.py (absolute paths).

Linux:
  Writes / removes a shell wrapper script at ~/.config/autostart/workwell.sh
  and a .desktop file at ~/.config/autostart/workwell.desktop.

  The wrapper script is used because:
    1. The project path contains spaces ("Study Volume"), which breaks the
       XDG Path= key on many DEs including Cinnamon.
    2. The venv Python must be used (system Python lacks PyQt6 etc.).
    3. A shell script handles both reliably via `cd` + explicit venv path.

All operations are safe to call multiple times (idempotent).
"""

import sys
import os
from pathlib import Path
from typing import Tuple

from src.utils.logger import get_logger
from src.utils.paths import get_platform, get_project_root

log = get_logger(__name__)

APP_NAME         = "WorkWell"
REGISTRY_KEY     = r"Software\Microsoft\Windows\CurrentVersion\Run"
DESKTOP_FILENAME = "workwell.desktop"
WRAPPER_FILENAME = "workwell.sh"


# ── Public API ────────────────────────────────────────────────────────────────

def enable_startup() -> Tuple[bool, str]:
    platform = get_platform()
    if platform == "windows":
        return _enable_windows()
    elif platform == "linux":
        return _enable_linux()
    else:
        msg = f"Startup integration not supported on {platform}."
        log.warning(msg)
        return False, msg


def disable_startup() -> Tuple[bool, str]:
    platform = get_platform()
    if platform == "windows":
        return _disable_windows()
    elif platform == "linux":
        return _disable_linux()
    else:
        msg = f"Startup integration not supported on {platform}."
        log.warning(msg)
        return False, msg


def is_startup_enabled() -> bool:
    platform = get_platform()
    if platform == "windows":
        return _check_windows()
    elif platform == "linux":
        return _check_linux()
    return False


# ── Windows ───────────────────────────────────────────────────────────────────

def _get_windows_command() -> str:
    python_exe = sys.executable
    main_py    = str(get_project_root() / "main.py")
    pythonw = python_exe.replace("python.exe", "pythonw.exe")
    if Path(pythonw).exists():
        python_exe = pythonw
    return f'"{python_exe}" "{main_py}"'


def _enable_windows() -> Tuple[bool, str]:
    try:
        import winreg
        cmd = _get_windows_command()
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REGISTRY_KEY,
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        msg = f"Startup enabled (registry): {cmd}"
        log.info(msg)
        return True, msg
    except Exception as exc:
        msg = f"Failed to enable Windows startup: {exc}"
        log.error(msg)
        return False, msg


def _disable_windows() -> Tuple[bool, str]:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REGISTRY_KEY,
            0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        msg = "Startup entry removed from registry."
        log.info(msg)
        return True, msg
    except FileNotFoundError:
        return True, "Startup entry was not present."
    except Exception as exc:
        msg = f"Failed to disable Windows startup: {exc}"
        log.error(msg)
        return False, msg


def _check_windows() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REGISTRY_KEY,
            0, winreg.KEY_READ
        )
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


# ── Linux ─────────────────────────────────────────────────────────────────────

def _get_autostart_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "autostart"


def _get_desktop_path() -> Path:
    return _get_autostart_dir() / DESKTOP_FILENAME


def _get_wrapper_path() -> Path:
    return _get_autostart_dir() / WRAPPER_FILENAME


def _build_wrapper_script() -> str:
    """
    Shell script that activates the venv and launches main.py.

    Using a wrapper solves two problems that plague .desktop files
    with spaces in paths:
      - 'cd' handles spaces correctly when the path is quoted in bash
      - Venv activation ensures the right Python + all dependencies

    IMPORTANT: do NOT call .resolve() on the venv Python path.
    .venv/bin/python is a symlink to the system Python, so resolving it
    strips the venv entirely and gives back /usr/bin/python3.x which has
    none of the project dependencies installed.
    """
    project_root = get_project_root().resolve()

    # Prefer the currently active venv via VIRTUAL_ENV env var (set whenever
    # the venv is active), so registration always captures the right env.
    # Fall back to the conventional .venv folder inside the project root.
    venv_dir = os.environ.get("VIRTUAL_ENV", "")
    if venv_dir:
        venv_python = str(Path(venv_dir) / "bin" / "python")
    else:
        venv_python = str(project_root / ".venv" / "bin" / "python")

    project_root_str = str(project_root)

    return (
        "#!/usr/bin/env bash\n"
        "# Auto-generated by WorkWell — do not edit manually.\n"
        "\n"
        "# Change to project root (quoted to handle spaces in path)\n"
        f'cd "{project_root_str}" || exit 1\n'
        "\n"
        "# Launch using the venv Python so all dependencies are available\n"
        f'exec "{venv_python}" main.py\n'
    )


def _build_desktop_entry(wrapper_path: Path) -> str:
    """
    .desktop file that calls the wrapper script.

    Exec= uses the wrapper path (no spaces — it lives in ~/.config/autostart).
    We deliberately avoid Path= because Cinnamon and several other DEs
    silently truncate it at the first space character.
    """
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        f"Name={APP_NAME}\n"
        "Comment=Health reminder — monitors sitting time\n"
        f"Exec={wrapper_path}\n"
        "Icon=\n"
        "Terminal=false\n"
        "Hidden=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "StartupNotify=false\n"
        "Categories=Utility;Health;\n"
    )


def _enable_linux() -> Tuple[bool, str]:
    try:
        autostart_dir = _get_autostart_dir()
        autostart_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write the wrapper script
        wrapper_path = _get_wrapper_path()
        wrapper_path.write_text(_build_wrapper_script(), encoding="utf-8")
        wrapper_path.chmod(0o755)   # must be executable

        # 2. Write the .desktop file pointing to the wrapper
        desktop_path = _get_desktop_path()
        desktop_path.write_text(
            _build_desktop_entry(wrapper_path), encoding="utf-8"
        )
        desktop_path.chmod(0o644)

        msg = f"Startup enabled: {desktop_path} -> {wrapper_path}"
        log.info(msg)
        return True, msg
    except Exception as exc:
        msg = f"Failed to enable Linux startup: {exc}"
        log.error(msg)
        return False, msg


def _disable_linux() -> Tuple[bool, str]:
    try:
        removed = []
        for path in (_get_desktop_path(), _get_wrapper_path()):
            if path.exists():
                path.unlink()
                removed.append(path.name)
        msg = (
            f"Startup entries removed: {', '.join(removed)}"
            if removed else "Startup entries were not present."
        )
        log.info(msg)
        return True, msg
    except Exception as exc:
        msg = f"Failed to disable Linux startup: {exc}"
        log.error(msg)
        return False, msg


def _check_linux() -> bool:
    # Both files must exist for startup to be considered enabled
    return _get_desktop_path().exists() and _get_wrapper_path().exists()
