"""
Safety module - Phase 5.

Leveled safety notices: none, notice, warning, critical.
Notice is no longer repeated in every answer.
"""

SAFETY_NOTICE = (
    "Safety notice: Power off before wiring or disconnecting. "
    "Confirm emergency stop, air supply, and equipment status before debugging. "
    "If unsure about equipment state, ask the instructor. "
    "Do not bypass safety circuits, short-circuit protection, or work on live equipment."
)

SAFETY_NOTICE_SHORT = (
    "Safety: Power off before any wiring work."
)

SAFETY_LEVELS = {
    "none": None,
    "notice": SAFETY_NOTICE_SHORT,
    "warning": SAFETY_NOTICE,
    "critical": (
        "CRITICAL SAFETY: Do not proceed without instructor supervision. "
        "Live equipment work requires proper PPE and lockout/tagout procedures."
    ),
}

HIGH_RISK_KEYWORDS = [
    "rewire", "modify wiring", "short circuit", "bypass safety",
    "override", "live measurement", "hot wire",
    "短接",
    "直接接",
    "带电接",
    "跳过安全",
    "停止安全",
    "带电操作",
    "不关电",
    "短接保护",
    "带电测量",
]

MEDIUM_RISK_KEYWORDS = [
    "connect", "wire", "power on", "measure", "test",
    "debug", "check wiring", "diagnose",
    "接线",
    "重新接",
    "换线",
    "换到",
    "排查故障",
    "检查接线",
]

LOW_RISK_KEYWORDS = [
    "what is", "explain", "difference", "concept",
    "principle", "function", "type", "definition",
]


def get_safety_level(text=""):
    """Determine safety level from message content.

    Returns one of: 'critical', 'warning', 'notice', 'none'
    """
    msg = str(text).lower() if text else ""

    # Check high risk
    for kw in HIGH_RISK_KEYWORDS:
        if kw.lower() in msg:
            return "warning"

    # Check medium risk
    for kw in MEDIUM_RISK_KEYWORDS:
        if kw.lower() in msg:
            return "notice"

    # Low risk: concept questions don't need safety notices
    for kw in LOW_RISK_KEYWORDS:
        if kw.lower() in msg:
            return "none"

    # Default: no safety notice for unknown content
    return "none"


def requires_safety_notice(text="", weak_abilities=None, recommended_path=None):
    """Check if safety notice is needed. Less aggressive than before."""
    level = get_safety_level(text)
    if level in ("warning", "critical"):
        return True
    if level == "notice":
        return True
    return False


def safety_notice(text="", weak_abilities=None, recommended_path=None):
    """Get the appropriate safety notice text for the given context."""
    level = get_safety_level(text)
    return SAFETY_LEVELS.get(level)
