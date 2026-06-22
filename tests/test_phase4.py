"""
tests/test_phase4.py

Standalone test for Phase 4 — ReminderPopup UI.

Launches the popup directly without needing the activity monitor,
tray icon, or any other app component. Useful for visual QA and
rapid iteration on the UI.

Usage (from project root):
    python tests/test_phase4.py
    python tests/test_phase4.py --minutes 42
    python tests/test_phase4.py --auto-close 5   # auto-close after 5 seconds

Keyboard shortcuts in the popup:
    Enter / Space  →  "OK, I'll take a break"
    Escape         →  "Skip for now"
"""

import sys
import argparse
import os

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from src.ui.reminder_popup import ReminderPopup


def main():
    parser = argparse.ArgumentParser(description="WorkWell Phase 4 popup test")
    parser.add_argument(
        "--minutes", type=int, default=37,
        help="Simulated elapsed sitting time in minutes (default: 37)"
    )
    parser.add_argument(
        "--auto-close", type=int, default=None, metavar="SECONDS",
        help="Automatically close after N seconds (for CI / screenshot testing)"
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("WorkWell")
    app.setQuitOnLastWindowClosed(False)

    popup = ReminderPopup(elapsed_minutes=args.minutes)

    # --- Signal callbacks ---
    def on_break():
        print(f"\n  ✅  User chose: take a break  (simulated {args.minutes} min session)")
        QTimer.singleShot(300, app.quit)

    def on_skip():
        print(f"\n  ⏭   User chose: skip reminder  (simulated {args.minutes} min session)")
        QTimer.singleShot(300, app.quit)

    popup.break_taken.connect(on_break)
    popup.skipped.connect(on_skip)

    # Show after event loop starts
    QTimer.singleShot(150, lambda: popup.show_popup(elapsed_minutes=args.minutes))

    # Optional auto-close
    if args.auto_close:
        QTimer.singleShot(args.auto_close * 1000, app.quit)
        print(f"  Auto-close in {args.auto_close}s…")

    print(f"\n  WorkWell — Phase 4 popup test")
    print(f"  Simulated sitting time : {args.minutes} minutes")
    print(f"  Press Enter/Space to 'take a break', Escape to 'skip'.\n")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
