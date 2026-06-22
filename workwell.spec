# workwell/workwell.spec
#
# PyInstaller build spec for WorkWell.
#
# Usage
# -----
#   pip install pyinstaller
#
#   # One-folder build (easier to debug):
#   pyinstaller workwell.spec
#
#   # Single-file build (set onefile=True below):
#   pyinstaller workwell.spec
#
# Output
# ------
#   dist/WorkWell/          (one-folder mode)
#   dist/WorkWell           (one-file mode, single executable)
#
# Notes
# -----
#   • Run from the project root (the directory that contains main.py).
#   • PyQt6 hidden imports are listed explicitly — PyInstaller sometimes
#     misses Qt platform plugins.
#   • The assets/ and config/ directories are bundled as data files so
#     the packaged app finds its icons and defaults.json.
#   • On Linux, the produced binary is portable across glibc-compatible
#     distros if built on an old-enough base image (e.g. Ubuntu 20.04).
#   • On Windows, add --uac-admin to the exe kwargs if you need elevation.

import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT      = Path(SPECPATH)          # project root (where this .spec lives)
MAIN      = str(ROOT / "main.py")
ICON_WIN  = str(ROOT / "assets" / "icons" / "tray.png")   # swap for .ico on Win
ICON_LIN  = str(ROOT / "assets" / "icons" / "tray.png")

# ── Data files ────────────────────────────────────────────────────────────────
# Tuples of (source_glob_or_path, dest_folder_inside_bundle)
datas = [
    (str(ROOT / "assets"),          "assets"),
    (str(ROOT / "config"),          "config"),
]

# ── Hidden imports ────────────────────────────────────────────────────────────
# PyQt6 platform plugins and other runtime-discovered modules
hidden_imports = [
    # PyQt6 essentials
    "PyQt6",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.sip",
    # Qt platform plugins (xcb on Linux, windows on Win)
    "PyQt6.QtDBus",
    # pynput backends
    "pynput.keyboard._xorg",
    "pynput.mouse._xorg",
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
    # stdlib / third-party that PyInstaller might miss
    "sqlite3",
    "json",
    "threading",
    "logging",
    "logging.handlers",
]

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    [MAIN],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy packages that WorkWell does not use at runtime
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "cv2",
        "test",
        "unittest",
        "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

# ── Executable ────────────────────────────────────────────────────────────────
onefile = False     # set True for a single-file build (slower startup)

if onefile:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="WorkWell",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,          # no terminal window
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=ICON_WIN if sys.platform == "win32" else None,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="WorkWell",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=ICON_WIN if sys.platform == "win32" else None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="WorkWell",
    )
