"""
workwell/src/ui/settings_window.py

Settings window for Phase 6.

Covers
------
  • Reminder interval (spin-box, 5–120 min)
  • Idle-reset threshold (spin-box, 1–30 min)
  • Snooze duration (spin-box, 5–60 min)
  • Launch on boot (checkbox)
  • Theme (dark / light combo-box)
  • Session logging enabled (checkbox)
  • AI assistant toggle + provider combo + model line-edit + API-key field
  • Save / Cancel buttons

Signals
-------
  settings_saved(dict)  — emitted with the full merged config dict after Save

Usage
-----
  win = SettingsWindow(config, parent=None)
  win.settings_saved.connect(on_settings_saved)
  win.show()              # or .exec() for modal
"""

from __future__ import annotations

import copy
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.utils.logger import get_logger

log = get_logger(__name__)

# ── QSS (matches Phase 4 dark theme) ─────────────────────────────────────────
_DARK_QSS = """
QDialog {
    background: #1a1a2e;
    color: #e0e0e0;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #2d2d4e;
    border-radius: 6px;
    background: #1e1e3a;
}
QTabBar::tab {
    background: #2d2d4e;
    color: #a0a0c0;
    padding: 8px 18px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    min-width: 80px;
}
QTabBar::tab:selected {
    background: #3d5afe;
    color: #ffffff;
}
QGroupBox {
    border: 1px solid #2d2d4e;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    color: #a0b0ff;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QLabel {
    color: #c0c8e8;
}
QSpinBox, QLineEdit, QComboBox {
    background: #2d2d4e;
    color: #e0e0f0;
    border: 1px solid #3d3d6e;
    border-radius: 5px;
    padding: 4px 8px;
    min-height: 26px;
}
QSpinBox:focus, QLineEdit:focus, QComboBox:focus {
    border: 1px solid #3d5afe;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background: #2d2d4e;
    color: #e0e0f0;
    selection-background-color: #3d5afe;
}
QCheckBox {
    color: #c0c8e8;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #5060a0;
    border-radius: 3px;
    background: #2d2d4e;
}
QCheckBox::indicator:checked {
    background: #3d5afe;
    border-color: #3d5afe;
}
QPushButton {
    background: #3d5afe;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 7px 20px;
    font-weight: bold;
    min-width: 80px;
}
QPushButton:hover  { background: #536dfe; }
QPushButton:pressed { background: #2962ff; }
QPushButton#btn_cancel {
    background: #2d2d4e;
    color: #a0a8c8;
    border: 1px solid #3d3d6e;
}
QPushButton#btn_cancel:hover { background: #3a3a5a; }
QScrollArea { border: none; background: transparent; }
"""

_LIGHT_QSS = """
QDialog {
    background: #f5f5f5;
    color: #1a1a2e;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #d0d0e0;
    border-radius: 6px;
    background: #ffffff;
}
QTabBar::tab {
    background: #e8e8f0;
    color: #505080;
    padding: 8px 18px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    min-width: 80px;
}
QTabBar::tab:selected {
    background: #3d5afe;
    color: #ffffff;
}
QGroupBox {
    border: 1px solid #d0d0e0;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    color: #3d5afe;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QLabel { color: #303050; }
QSpinBox, QLineEdit, QComboBox {
    background: #ffffff;
    color: #1a1a2e;
    border: 1px solid #b0b0c8;
    border-radius: 5px;
    padding: 4px 8px;
    min-height: 26px;
}
QSpinBox:focus, QLineEdit:focus, QComboBox:focus { border: 1px solid #3d5afe; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #1a1a2e;
    selection-background-color: #3d5afe;
    selection-color: #ffffff;
}
QCheckBox { color: #303050; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #8080b0; border-radius: 3px; background: #ffffff;
}
QCheckBox::indicator:checked { background: #3d5afe; border-color: #3d5afe; }
QPushButton {
    background: #3d5afe; color: #ffffff;
    border: none; border-radius: 6px;
    padding: 7px 20px; font-weight: bold; min-width: 80px;
}
QPushButton:hover  { background: #536dfe; }
QPushButton:pressed { background: #2962ff; }
QPushButton#btn_cancel {
    background: #e8e8f0; color: #505080; border: 1px solid #c0c0d8;
}
QPushButton#btn_cancel:hover { background: #d8d8e8; }
QScrollArea { border: none; background: transparent; }
"""


class SettingsWindow(QDialog):
    """Modal settings dialog.

    Parameters
    ----------
    config : dict
        The live config dict (a deep-copy is made internally; the original
        is never mutated until the user clicks Save).
    parent : QWidget | None
    """

    settings_saved = pyqtSignal(dict)   # emitted with the full new config

    def __init__(self, config: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = copy.deepcopy(config)
        self._theme  = config.get("appearance", {}).get("theme", "dark")

        self.setWindowTitle("WorkWell — Settings")
        self.setMinimumWidth(480)
        self.setMinimumHeight(420)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self._build_ui()
        self._apply_theme(self._theme)
        self._load_values()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Title bar
        title = QLabel("⚙  Settings")
        f = title.font()
        f.setPointSize(15)
        f.setBold(True)
        title.setFont(f)
        root.addWidget(title)

        # Tab widget
        self._tabs = QTabWidget()
        root.addWidget(self._tabs)

        self._tabs.addTab(self._build_general_tab(),   "General")
        self._tabs.addTab(self._build_ai_tab(),        "AI Assistant")
        self._tabs.addTab(self._build_advanced_tab(),  "Advanced")

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.setObjectName("btn_cancel")
        self._btn_cancel.clicked.connect(self.reject)

        self._btn_save = QPushButton("Save")
        self._btn_save.clicked.connect(self._on_save)

        btn_row.addWidget(self._btn_cancel)
        btn_row.addWidget(self._btn_save)
        root.addLayout(btn_row)

    # ── Tab: General ──────────────────────────────────────────────────────────

    def _build_general_tab(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(12)

        # ── Reminder group ────────────────────────────────────────────────────
        grp_reminder = QGroupBox("Reminder")
        form_r = QFormLayout(grp_reminder)
        form_r.setSpacing(10)

        self._spin_interval = QSpinBox()
        self._spin_interval.setRange(5, 120)
        self._spin_interval.setSuffix("  min")
        self._spin_interval.setToolTip(
            "How many active minutes before WorkWell shows a reminder."
        )
        form_r.addRow("Reminder interval:", self._spin_interval)

        self._spin_idle = QSpinBox()
        self._spin_idle.setRange(1, 30)
        self._spin_idle.setSuffix("  min")
        self._spin_idle.setToolTip(
            "If you haven't touched the keyboard/mouse for this long, "
            "the active-time timer resets."
        )
        form_r.addRow("Idle-reset after:", self._spin_idle)

        self._spin_snooze = QSpinBox()
        self._spin_snooze.setRange(5, 60)
        self._spin_snooze.setSuffix("  min")
        self._spin_snooze.setToolTip(
            "When you click 'Skip', the next reminder is delayed by this many minutes."
        )
        form_r.addRow("Snooze duration:", self._spin_snooze)

        vbox.addWidget(grp_reminder)

        # ── Startup / appearance group ────────────────────────────────────────
        grp_app = QGroupBox("Application")
        form_a = QFormLayout(grp_app)
        form_a.setSpacing(10)

        self._chk_boot = QCheckBox("Launch WorkWell when the computer starts")
        form_a.addRow(self._chk_boot)

        self._cmb_theme = QComboBox()
        self._cmb_theme.addItems(["dark", "light"])
        self._cmb_theme.setToolTip(
            "Theme change applies to the popup and settings window. "
            "Restart the app to update the tray tooltip colour."
        )
        self._cmb_theme.currentTextChanged.connect(self._on_theme_preview)
        form_a.addRow("Theme:", self._cmb_theme)

        vbox.addWidget(grp_app)
        vbox.addStretch()
        return page

    # ── Tab: AI Assistant ─────────────────────────────────────────────────────

    def _build_ai_tab(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(12)

        grp = QGroupBox("AI Health Assistant (Phase 5)")
        form = QFormLayout(grp)
        form.setSpacing(10)

        self._chk_ai = QCheckBox("Enable AI chatbot in reminder popup")
        form.addRow(self._chk_ai)

        self._cmb_provider = QComboBox()
        self._cmb_provider.addItems(["openai", "gemini"])
        form.addRow("Provider:", self._cmb_provider)

        self._edit_model = QLineEdit()
        self._edit_model.setPlaceholderText("e.g. gpt-4o-mini")
        form.addRow("Model:", self._edit_model)

        self._edit_key = QLineEdit()
        self._edit_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit_key.setPlaceholderText("Paste your API key here")
        form.addRow("API key:", self._edit_key)

        # Show / hide toggle
        btn_toggle_key = QPushButton("Show")
        btn_toggle_key.setFixedWidth(60)
        btn_toggle_key.setCheckable(True)

        def _toggle_echo(checked: bool) -> None:
            btn_toggle_key.setText("Hide" if checked else "Show")
            self._edit_key.setEchoMode(
                QLineEdit.EchoMode.Normal if checked
                else QLineEdit.EchoMode.Password
            )

        btn_toggle_key.toggled.connect(_toggle_echo)

        key_row = QHBoxLayout()
        key_row.addWidget(self._edit_key)
        key_row.addWidget(btn_toggle_key)
        # Replace the simple row with the composite one
        # (remove the last row and re-add)
        form.removeRow(form.rowCount() - 1)
        form.addRow("API key:", key_row)

        note = QLabel(
            "The API key is stored in your local config file only.\n"
            "WorkWell never transmits it to any server other than the chosen AI provider."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #7080a0; font-size: 11px;")
        form.addRow(note)

        vbox.addWidget(grp)
        vbox.addStretch()
        return page

    # ── Tab: Advanced ─────────────────────────────────────────────────────────

    def _build_advanced_tab(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(12)

        grp = QGroupBox("Session Logging")
        form = QFormLayout(grp)
        form.setSpacing(10)

        self._chk_log_enabled = QCheckBox("Enable session logging (SQLite)")
        self._chk_log_enabled.setToolTip(
            "Records every reminder + response (break / skip) "
            "in a local SQLite database for future analytics."
        )
        form.addRow(self._chk_log_enabled)

        self._chk_log_responses = QCheckBox("Log break / skip responses")
        self._chk_log_responses.setToolTip(
            "When enabled, the specific user choice (break taken or skipped) "
            "is written to the log, not just that a reminder was shown."
        )
        form.addRow(self._chk_log_responses)

        vbox.addWidget(grp)

        # ── Log level group ───────────────────────────────────────────────────
        grp_ll = QGroupBox("Developer / Debug")
        form_ll = QFormLayout(grp_ll)
        form_ll.setSpacing(10)

        self._cmb_log_level = QComboBox()
        self._cmb_log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self._cmb_log_level.setToolTip("File / console log verbosity.")
        form_ll.addRow("Log level:", self._cmb_log_level)

        vbox.addWidget(grp_ll)
        vbox.addStretch()
        return page

    # ── Load / Save ──────────────────────────────────────────────────────────

    def _load_values(self) -> None:
        """Populate all controls from self._config."""
        r = self._config.get("reminder", {})
        self._spin_interval.setValue(r.get("interval_minutes", 35))
        self._spin_idle.setValue(r.get("idle_reset_minutes", 5))
        self._spin_snooze.setValue(r.get("snooze_minutes", 15))

        s = self._config.get("startup", {})
        self._chk_boot.setChecked(s.get("launch_on_boot", True))

        a = self._config.get("appearance", {})
        idx = self._cmb_theme.findText(a.get("theme", "dark"))
        if idx >= 0:
            self._cmb_theme.setCurrentIndex(idx)

        ai = self._config.get("ai_assistant", {})
        self._chk_ai.setChecked(ai.get("enabled", False))
        provider_idx = self._cmb_provider.findText(ai.get("provider", "openai"))
        if provider_idx >= 0:
            self._cmb_provider.setCurrentIndex(provider_idx)
        self._edit_model.setText(ai.get("model", "gpt-4o-mini"))
        self._edit_key.setText(ai.get("api_key", ""))

        lg = self._config.get("logging", {})
        self._chk_log_enabled.setChecked(lg.get("enabled", True))
        self._chk_log_responses.setChecked(lg.get("log_responses", True))
        ll_idx = self._cmb_log_level.findText(lg.get("log_level", "INFO"))
        if ll_idx >= 0:
            self._cmb_log_level.setCurrentIndex(ll_idx)

    def _collect_values(self) -> dict[str, Any]:
        """Read all controls and return a fully merged config dict."""
        cfg = copy.deepcopy(self._config)

        cfg.setdefault("reminder",    {})
        cfg.setdefault("startup",     {})
        cfg.setdefault("appearance",  {})
        cfg.setdefault("ai_assistant",{})
        cfg.setdefault("logging",     {})

        cfg["reminder"]["interval_minutes"] = self._spin_interval.value()
        cfg["reminder"]["idle_reset_minutes"] = self._spin_idle.value()
        cfg["reminder"]["snooze_minutes"]   = self._spin_snooze.value()

        cfg["startup"]["launch_on_boot"]    = self._chk_boot.isChecked()

        cfg["appearance"]["theme"]          = self._cmb_theme.currentText()

        cfg["ai_assistant"]["enabled"]      = self._chk_ai.isChecked()
        cfg["ai_assistant"]["provider"]     = self._cmb_provider.currentText()
        cfg["ai_assistant"]["model"]        = self._edit_model.text().strip()
        cfg["ai_assistant"]["api_key"]      = self._edit_key.text().strip()

        cfg["logging"]["enabled"]           = self._chk_log_enabled.isChecked()
        cfg["logging"]["log_responses"]     = self._chk_log_responses.isChecked()
        cfg["logging"]["log_level"]         = self._cmb_log_level.currentText()

        return cfg

    def _on_save(self) -> None:
        new_cfg = self._collect_values()
        log.info("SettingsWindow: settings saved.")
        self.settings_saved.emit(new_cfg)
        self.accept()

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _on_theme_preview(self, theme: str) -> None:
        """Live-preview the theme while the user is choosing."""
        self._apply_theme(theme)

    def _apply_theme(self, theme: str) -> None:
        self.setStyleSheet(_DARK_QSS if theme == "dark" else _LIGHT_QSS)
