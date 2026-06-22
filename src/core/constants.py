"""
workwell/src/core/constants.py

Single source of truth for all application-wide constants.
Import from here; never scatter magic numbers through the codebase.
"""

APP_NAME    = "WorkWell"
APP_VERSION = "0.1.0"
APP_AUTHOR  = "WorkWell Personal"

# ── Timing ──────────────────────────────────────────────────────────────────
DEFAULT_REMINDER_INTERVAL_MINUTES = 35   # fires after this many active minutes
DEFAULT_IDLE_RESET_MINUTES        = 5    # reset session if idle this long
DEFAULT_SNOOZE_MINUTES            = 15   # skip-for-now duration
ACTIVITY_POLL_INTERVAL_MS         = 1000 # how often the monitor ticks (1 s)

# ── UI ───────────────────────────────────────────────────────────────────────
POPUP_SCREEN_FRACTION  = 0.75   # popup covers 75 % of the screen
FACT_ROTATION_SECS     = 8      # seconds between rotating health facts
TIPS_AUTOSCROLL_SECS   = 4      # seconds between auto-scroll steps in sidebar

# ── Tray ─────────────────────────────────────────────────────────────────────
TRAY_TOOLTIP = f"{APP_NAME} — health reminder running"

# ── Logging ──────────────────────────────────────────────────────────────────
DEFAULT_LOG_LEVEL = "INFO"

# ── Health content ───────────────────────────────────────────────────────────
ROTATING_FACTS = [
    "A simple mobility break can significantly reduce back pain risk.",
    "Long sitting sessions contribute to neck, spine, and posture problems.",
    "Standing and stretching for 2–5 minutes improves circulation and focus.",
    "Shoulder rolls and wrist circles take under 60 seconds and relieve tension.",
    "The 20-20-20 rule: every 20 min, look 20 feet away for 20 seconds.",
    "Staying hydrated reduces muscle fatigue and helps maintain focus.",
    "A short walk between tasks can boost creativity and problem-solving.",
    "Deep breathing for 60 seconds lowers cortisol and reduces eye strain.",
]

HEALTH_TIPS = [
    {
        "title": "Posture check",
        "body": (
            "Ears over shoulders, shoulders over hips. "
            "Your lower back should gently touch the chair back."
        ),
    },
    {
        "title": "Neck release",
        "body": (
            "Slowly tilt your head to the right, hold 10 s, then left. "
            "Repeat twice each side."
        ),
    },
    {
        "title": "Shoulder rolls",
        "body": (
            "Roll both shoulders forward 5 times, then backward 5 times. "
            "Relieves upper-back tension from typing."
        ),
    },
    {
        "title": "Eye strain — 20-20-20",
        "body": (
            "Every 20 minutes, look at something 20 feet away for 20 seconds. "
            "Reduces digital eye fatigue."
        ),
    },
    {
        "title": "Wrist stretch",
        "body": (
            "Extend one arm, palm up. Gently pull fingers down with the other hand. "
            "Hold 15 s each side."
        ),
    },
    {
        "title": "Hip flexor release",
        "body": (
            "Stand and step one foot forward into a shallow lunge. "
            "Hold 20 s each side to counter prolonged hip flexion."
        ),
    },
    {
        "title": "Hydration reminder",
        "body": (
            "Dehydration worsens focus and posture fatigue. "
            "A glass of water now is a good habit."
        ),
    },
    {
        "title": "Chest opener",
        "body": (
            "Clasp hands behind your back, squeeze shoulder blades together, "
            "and lift slightly. Hold 10 s. Counters screen-forward posture."
        ),
    },
    {
        "title": "Workspace ergonomics",
        "body": (
            "Monitor top should be at or just below eye level. "
            "Keep it an arm's length away to reduce neck and eye strain."
        ),
    },
    {
        "title": "Chin tuck",
        "body": (
            "Draw your chin straight back (not down). "
            "Do 10 slow reps to realign the cervical spine."
        ),
    },
]
