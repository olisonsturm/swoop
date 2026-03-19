"""Shared formatting helpers used by both core dataclass repr and CLI output."""

from typing import Tuple


def fmt_clock(t: Tuple[int, ...]) -> str:
    """Format a time tuple like (8, 30) as '08:30'."""
    h = t[0] if len(t) > 0 else 0
    m = t[1] if len(t) > 1 else 0
    return f"{h:02d}:{m:02d}"


def fmt_duration(minutes: int) -> str:
    """Format minutes as '5h 15m'.

    Returns '0m' for zero/negative, omits the minutes part when even hours,
    and omits the hours part when under 60 minutes.
    """
    if minutes <= 0:
        return "0m"
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h {m:02d}m"
    if h:
        return f"{h}h"
    return f"{m}m"
