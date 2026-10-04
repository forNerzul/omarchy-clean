"""Pure state model for the overlay (no GTK)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace

from omarchy_clean.core import MAX_LOCK_SECONDS

AUTH_DISMISSED_CODES = (126, 127)


def parse_status_line(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    if not isinstance(obj, dict) or not isinstance(obj.get("event"), str):
        return None
    return obj


def format_remaining(seconds: float) -> str:
    total = max(0, math.ceil(seconds))
    return f"{total // 60}:{total % 60:02d}"


UNLIMITED_HEADLINE = "No time limit"
UNLOCK_HINT = "Hold Esc + Enter for 3 seconds to unlock"


def parse_duration_arg(text: str) -> tuple[int, bool]:
    """Parse the CLI duration into (seconds, unlimited)."""
    if text.strip().lower() == "unlimited":
        return MAX_LOCK_SECONDS, True
    try:
        n = int(text)
    except ValueError:
        raise ValueError(
            f"invalid duration {text!r}: use 1..{MAX_LOCK_SECONDS} or 'unlimited'"
        ) from None
    if not 1 <= n <= MAX_LOCK_SECONDS:
        raise ValueError(f"duration must be between 1 and {MAX_LOCK_SECONDS}")
    return n, False


@dataclass(frozen=True)
class OverlayState:
    phase: str = "authorizing"
    remaining: float = 0.0
    combo: float = 0.0
    reason: str | None = None
    message: str | None = None
    unlimited: bool = False


def apply_event(state: OverlayState, event: dict) -> OverlayState:
    kind = event.get("event")
    if kind == "locked":
        return replace(state, phase="locked", remaining=event.get("duration", 0.0))
    if kind == "tick" and state.phase == "locked":
        return replace(
            state,
            remaining=event.get("remaining", state.remaining),
            combo=event.get("combo", state.combo),
        )
    if kind == "error":
        return replace(state, message=event.get("message"))
    if kind == "unlocked":
        return replace(state, phase="unlocked", reason=event.get("reason"))
    return state


def helper_exit_outcome(state: OverlayState, exit_code: int) -> OverlayState:
    if state.phase == "unlocked":
        return state
    if state.phase == "authorizing" and exit_code in AUTH_DISMISSED_CODES:
        return replace(state, phase="cancelled")
    message = state.message or f"helper exited with code {exit_code}"
    return replace(state, phase="failed", message=message)


def locked_labels(state: OverlayState) -> tuple[str, str, str | None]:
    """Return (headline, hint, footnote) for the locked screen."""
    if state.unlimited:
        return (
            UNLIMITED_HEADLINE,
            UNLOCK_HINT,
            f"Releases automatically in {format_remaining(state.remaining)}",
        )
    return format_remaining(state.remaining), UNLOCK_HINT, None
