"""Pure state model for the overlay (no GTK)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace

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


@dataclass(frozen=True)
class OverlayState:
    phase: str = "authorizing"
    remaining: float = 0.0
    combo: float = 0.0
    reason: str | None = None
    message: str | None = None


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
