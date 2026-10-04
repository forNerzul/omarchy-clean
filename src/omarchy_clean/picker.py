"""Duration picker backed by the native Omarchy menu (no GTK)."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable

from omarchy_clean.overlay_model import parse_duration_arg

PICKER_COMMAND = "omarchy-menu-select"
PICKER_PROMPT = "Lock keyboard for"
FALLBACK_DURATION = "60"
PICKER_OPTIONS: tuple[tuple[str, str], ...] = (
    ("30 seconds", "30"),
    ("1 minute", "60"),
    ("2 minutes", "120"),
    ("5 minutes", "300"),
    ("No limit (Esc + Enter)", "unlimited"),
)


def pick_duration(*, run=subprocess.run, which=shutil.which) -> str | None:
    """Ask the user for a duration; None means cancelled."""
    if which(PICKER_COMMAND) is None:
        return FALLBACK_DURATION
    labels = [label for label, _ in PICKER_OPTIONS]
    argv = [PICKER_COMMAND, PICKER_PROMPT, *labels, "--", "--width", "360"]
    try:
        result = run(argv, capture_output=True, text=True)
    except OSError:
        return FALLBACK_DURATION
    if result.returncode != 0:
        return None
    lines = result.stdout.strip().splitlines()
    choice = lines[0].strip() if lines else ""
    return dict(PICKER_OPTIONS).get(choice)


def resolve_duration(
    value: str | None, pick: Callable[[], str | None] = pick_duration
) -> tuple[int, bool] | None:
    """Parse an explicit duration, or ask the picker; None means cancelled."""
    if value is None:
        value = pick()
        if value is None:
            return None
    return parse_duration_arg(value)
