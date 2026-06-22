"""
src/ui/reminder_popup.py

Phase 4 — Full-Screen Reminder Popup UI
WorkWell Desktop Health Reminder Application

BUG FIX (v2): The original two-window approach (overlay + card as separate
windows) caused a focus-trap on Linux — clicking outside the card focused the
overlay window, which had no input handlers, locking the user out entirely.

Fix: Single full-screen window. The dim background is painted directly inside
ReminderPopup.paintEvent(). The card is a child QWidget centred on top.
There is now only one window, so focus can never escape to a dead overlay.
"""

import random
import logging

from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFrame,
    QScrollArea, QApplication, QGraphicsOpacityEffect,
    QSizePolicy,
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    pyqtSignal, QRect,
)
from PyQt6.QtGui import QColor, QPainter

from src.core.health_content import HEALTH_FACTS, SIDEBAR_TIPS

log = logging.getLogger("workwell.reminder_popup")


# ── QSS stylesheet ─────────────────────────────────────────────────────────────

_QSS = """
QWidget#ReminderCard {
    background-color: #1a1d2e;
    border-radius: 20px;
    border: 1px solid #2e3250;
}
QLabel#Badge {
    color: #6c73e6;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
    font-family: 'Segoe UI', 'Ubuntu', sans-serif;
}
QLabel#Heading {
    color: #ffffff;
    font-size: 26px;
    font-weight: 700;
    font-family: 'Segoe UI', 'Ubuntu', sans-serif;
}
QLabel#SubHeading {
    color: #a0a8d0;
    font-size: 13px;
    font-family: 'Segoe UI', 'Ubuntu', sans-serif;
}
QLabel#FactLabel {
    color: #e8ebff;
    font-size: 14px;
    font-style: italic;
    font-family: 'Segoe UI', 'Ubuntu', sans-serif;
    background-color: #252840;
    border-radius: 10px;
    padding: 12px 18px;
    border-left: 4px solid #6c73e6;
}
QLabel#TimerBig {
    color: #ff8c69;
    font-size: 48px;
    font-weight: 800;
    font-family: 'Segoe UI', 'Ubuntu', sans-serif;
}
QLabel#TimerSub {
    color: #a0a8d0;
    font-size: 12px;
    font-family: 'Segoe UI', 'Ubuntu', sans-serif;
}
QPushButton#BreakBtn {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #4f67e4, stop:1 #6c8bf5);
    color: #ffffff;
    font-size: 16px;
    font-weight: 700;
    font-family: 'Segoe UI', 'Ubuntu', sans-serif;
    border: none;
    border-radius: 12px;
    padding: 14px 32px;
    min-width: 230px;
}
QPushButton#BreakBtn:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #5f77f4, stop:1 #7c9bff);
}
QPushButton#BreakBtn:pressed {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #3f57d4, stop:1 #5c7be5);
}
QPushButton#SkipBtn {
    background-color: transparent;
    color: #7880b0;
    font-size: 13px;
    font-family: 'Segoe UI', 'Ubuntu', sans-serif;
    border: 1px solid #3a3f60;
    border-radius: 10px;
    padding: 10px 24px;
    min-width: 160px;
}
QPushButton#SkipBtn:hover {
    background-color: #252840;
    color: #a0a8d0;
    border-color: #6c73e6;
}
QPushButton#SkipBtn:pressed {
    background-color: #1e2138;
}
QFrame#Sidebar {
    background-color: #151728;
    border-radius: 14px;
    border: 1px solid #2a2e50;
}
QLabel#SidebarHeader {
    color: #6c73e6;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
    font-family: 'Segoe UI', 'Ubuntu', sans-serif;
}
QLabel#CategoryLbl {
    color: #6c73e6;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
    font-family: 'Segoe UI', 'Ubuntu', sans-serif;
    padding-top: 10px;
}
QLabel#TipTitle {
    color: #d0d5f0;
    font-size: 13px;
    font-weight: 700;
    font-family: 'Segoe UI', 'Ubuntu', sans-serif;
}
QLabel#TipItem {
    color: #9099c4;
    font-size: 12px;
    font-family: 'Segoe UI', 'Ubuntu', sans-serif;
    padding-left: 10px;
}
QFrame#Divider {
    background-color: #2a2e50;
    max-height: 1px;
}
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical {
    background: #1e2138; width: 6px; border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #3a3f60; border-radius: 3px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #6c73e6; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


# ── Rotating health fact label ─────────────────────────────────────────────────

class RotatingFactLabel(QLabel):
    """Cross-fades through HEALTH_FACTS every 6 seconds."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FactLabel")
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._facts = HEALTH_FACTS[:]
        random.shuffle(self._facts)
        self._idx = 0
        self.setText(self._facts[0])

        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._fx.setOpacity(1.0)

        self._anim = QPropertyAnimation(self._fx, b"opacity")
        self._anim.setDuration(600)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._fading_out = False
        self._anim.finished.connect(self._on_anim_done)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._start_fade_out)
        self._timer.start(6000)

    def _start_fade_out(self):
        self._fading_out = True
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _on_anim_done(self):
        if self._fading_out:
            self._idx = (self._idx + 1) % len(self._facts)
            self.setText(self._facts[self._idx])
            self._fading_out = False
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.start()


# ── Session timer display ──────────────────────────────────────────────────────

class SessionTimerDisplay(QWidget):
    """Shows elapsed sitting time, e.g. '37' with 'minutes sitting' below."""

    def __init__(self, elapsed_minutes: int = 0, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._big = QLabel(str(elapsed_minutes))
        self._big.setObjectName("TimerBig")
        layout.addWidget(self._big)

        sub = QLabel("minutes sitting")
        sub.setObjectName("TimerSub")
        layout.addWidget(sub)

    def set_minutes(self, minutes: int):
        self._big.setText(str(minutes))


# ── Health tips sidebar ────────────────────────────────────────────────────────

class HealthSidebar(QFrame):
    """
    Right-side panel with a scrollable list of health tips.
    Auto-scrolls slowly; pauses on mouse hover or manual drag.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self._paused = False
        self._build()
        self._start_autoscroll()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 10, 14)
        layout.setSpacing(0)

        hdr = QLabel("💡  HEALTH & MOBILITY TIPS")
        hdr.setObjectName("SidebarHeader")
        layout.addWidget(hdr)

        div = QFrame()
        div.setObjectName("Divider")
        div.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(div)
        layout.addSpacing(6)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 6, 20)
        inner_layout.setSpacing(2)

        tips_shuffled = SIDEBAR_TIPS[:]
        random.shuffle(tips_shuffled)

        for section in tips_shuffled:
            cat = QLabel(section["category"])
            cat.setObjectName("CategoryLbl")
            cat.setWordWrap(True)
            inner_layout.addWidget(cat)

            title = QLabel(section["title"])
            title.setObjectName("TipTitle")
            inner_layout.addWidget(title)

            for tip in section["tips"]:
                item = QLabel(f"• {tip}")
                item.setObjectName("TipItem")
                item.setWordWrap(True)
                inner_layout.addWidget(item)

            inner_layout.addSpacing(4)

        inner_layout.addStretch()
        self._scroll.setWidget(inner)
        layout.addWidget(self._scroll)

        bar = self._scroll.verticalScrollBar()
        bar.sliderPressed.connect(lambda: setattr(self, "_paused", True))
        bar.sliderReleased.connect(self._schedule_resume)

    def _start_autoscroll(self):
        self._scroll_timer = QTimer(self)
        self._scroll_timer.timeout.connect(self._step)
        self._scroll_timer.start(60)

        self._resume_timer = QTimer(self)
        self._resume_timer.setSingleShot(True)
        self._resume_timer.timeout.connect(
            lambda: setattr(self, "_paused", False))

    def _step(self):
        if self._paused:
            return
        bar = self._scroll.verticalScrollBar()
        if bar.value() >= bar.maximum():
            bar.setValue(0)
        else:
            bar.setValue(bar.value() + 1)

    def _schedule_resume(self):
        self._resume_timer.start(3000)

    def enterEvent(self, e):
        self._paused = True
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._resume_timer.start(600)
        super().leaveEvent(e)


# ── Main popup window ──────────────────────────────────────────────────────────

class ReminderPopup(QWidget):
    """
    Phase 4 full-screen reminder popup — single-window design.

    The entire screen is covered by this one FramelessWindowHint window.
    paintEvent() draws the semi-transparent dark background.
    The card (_card) is a plain child QWidget positioned in the centre.

    This eliminates the focus-trap bug that occurred when a separate overlay
    window stole focus and had no way to dismiss it.

    Signals
    -------
    break_taken  — user clicked "OK, I'll take a break"
    skipped      — user clicked "Skip for now" (or pressed Escape)

    Public API
    ----------
    show_popup(elapsed_minutes)  — show full-screen window
    close_popup()                — hide it
    set_elapsed_minutes(n)       — update the timer display while visible
    """

    break_taken = pyqtSignal()
    skipped     = pyqtSignal()

    def __init__(self, elapsed_minutes: int = 0, parent=None):
        super().__init__(parent)
        self._elapsed = elapsed_minutes
        self._build_window()
        self._card.setStyleSheet(_QSS)

    # ── Window setup ──────────────────────────────────────────────────────────

    def _build_window(self):
        # Full-screen, frameless, always on top, translucent so we can
        # paint our own dim background in paintEvent.
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Cover the entire primary screen
        screen_geo = QApplication.primaryScreen().geometry()
        self.setGeometry(screen_geo)

        # Card dimensions: 76% × 78% of screen, centred
        sw, sh = screen_geo.width(), screen_geo.height()
        cw = int(sw * 0.76)
        ch = int(sh * 0.78)
        cx = (sw - cw) // 2
        cy = (sh - ch) // 2

        # The card is a child widget — it sits on top of our painted background
        self._card = QWidget(self)
        self._card.setObjectName("ReminderCard")
        self._card.setGeometry(cx, cy, cw, ch)

        # Layout inside the card
        root = QHBoxLayout(self._card)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(24)
        root.addLayout(self._build_left_column(), stretch=1)
        root.addWidget(self._build_sidebar(), stretch=0)

    # ── Dim background ────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        """Paint a semi-transparent dark overlay across the full window."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        overlay = QColor(0, 0, 0)
        overlay.setAlphaF(0.75)
        p.fillRect(self.rect(), overlay)

    # ── Content ───────────────────────────────────────────────────────────────

    def _build_left_column(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(16)

        badge = QLabel("WorkWell  🌿")
        badge.setObjectName("Badge")
        col.addWidget(badge)

        heading = QLabel("You've been sitting for too long!")
        heading.setObjectName("Heading")
        heading.setWordWrap(True)
        col.addWidget(heading)

        sub = QLabel("Time to move, stretch, and reset your body. 🧘")
        sub.setObjectName("SubHeading")
        col.addWidget(sub)

        div = QFrame()
        div.setObjectName("Divider")
        div.setFrameShape(QFrame.Shape.HLine)
        col.addWidget(div)

        self._timer_display = SessionTimerDisplay(self._elapsed)
        col.addWidget(self._timer_display)

        self._fact_label = RotatingFactLabel()
        col.addWidget(self._fact_label)

        col.addStretch()

        self._break_btn = QPushButton("✅   OK, I'll take a break")
        self._break_btn.setObjectName("BreakBtn")
        self._break_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._break_btn.clicked.connect(self._on_break)
        col.addWidget(self._break_btn)

        self._skip_btn = QPushButton("⏭   Skip for now")
        self._skip_btn.setObjectName("SkipBtn")
        self._skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._skip_btn.clicked.connect(self._on_skip)
        col.addWidget(self._skip_btn)

        return col

    def _build_sidebar(self) -> HealthSidebar:
        sw = QApplication.primaryScreen().geometry().width()
        sidebar_w = max(280, int(sw * 0.76 * 0.33))
        self._sidebar = HealthSidebar()
        self._sidebar.setFixedWidth(sidebar_w)
        self._sidebar.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        return self._sidebar

    # ── Public API ────────────────────────────────────────────────────────────

    def show_popup(self, elapsed_minutes: int = None):
        """Show the full-screen popup."""
        if elapsed_minutes is not None:
            self.set_elapsed_minutes(elapsed_minutes)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        log.info("ReminderPopup shown (elapsed=%d min)", self._elapsed)

    def close_popup(self):
        """Hide the popup."""
        self.hide()
        log.info("ReminderPopup closed")

    def set_elapsed_minutes(self, minutes: int):
        self._elapsed = minutes
        self._timer_display.set_minutes(minutes)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_break(self):
        log.info("User chose: take a break")
        self.break_taken.emit()
        self.close_popup()

    def _on_skip(self):
        log.info("User chose: skip reminder")
        self.skipped.emit()
        self.close_popup()

    # ── Keyboard shortcuts ────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._on_skip()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            self._on_break()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        # Window manager close → treat as skip
        self._on_skip()
        event.ignore()
