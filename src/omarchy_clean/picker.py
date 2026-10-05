"""Duration picker backed by the native Omarchy menu (no GTK)."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from omarchy_clean.overlay_model import parse_duration_arg

PICKER_COMMAND = "omarchy-menu-select"
PICKER_PROMPT = "Lock keyboard for"
FALLBACK_DURATION = "60"
SHELL_COMMAND = "omarchy-shell"
PING_COMMAND = [SHELL_COMMAND, "shell", "ping"]
PING_IPC_TIMEOUT = "0.5s"
PING_TIMEOUT_SECONDS = 3
PICKER_TIMEOUT_SECONDS = 120
STDERR_LIMIT = 2000
NOTIFY_MESSAGE = (
    "Could not open the duration menu. Locking for 1 minute. "
    "Details: omarchy-clean --diagnose"
)
NOTIFY_NO_LOCK_MESSAGE = (
    "The duration menu did not finish. Nothing was locked. "
    "Details: omarchy-clean --diagnose"
)
# The menu may have been shown to the user, so never lock on these.
NO_LOCK_REASONS = frozenset({"timeout", "stderr"})
PICKER_OPTIONS: tuple[tuple[str, str], ...] = (
    ("30 seconds", "30"),
    ("1 minute", "60"),
    ("2 minutes", "120"),
    ("5 minutes", "300"),
    ("No limit (Esc + Enter)", "unlimited"),
)


@dataclass(frozen=True)
class PickFailure:
    reason: str  # shell-unresponsive, timeout, exit-code, stderr, unknown-choice, os-error
    returncode: int | None
    stderr: str
    detail: str


@dataclass(frozen=True)
class PickResult:
    """duration None with no failure means the user cancelled.

    A failure with duration None means the menu may have been shown: do not lock.
    """

    duration: str | None
    failure: PickFailure | None = None


def _failure(reason, detail, returncode=None, stderr="") -> PickResult:
    duration = None if reason in NO_LOCK_REASONS else FALLBACK_DURATION
    return PickResult(
        duration,
        PickFailure(reason, returncode, (stderr or "")[:STDERR_LIMIT], detail),
    )


def _shell_responds(run, environ: Mapping[str, str]) -> tuple[bool, str]:
    env = {**environ, "OMARCHY_SHELL_IPC_TIMEOUT": PING_IPC_TIMEOUT}
    try:
        result = run(PING_COMMAND, capture_output=True, text=True, env=env,
                     timeout=PING_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return False, "the shell ping timed out"
    except OSError as exc:
        return False, f"the shell ping could not run: {exc}"
    if result.returncode != 0:
        return False, f"the shell ping exited with code {result.returncode}"
    return True, ""


def pick_duration(*, run=subprocess.run, which=shutil.which,
                  environ: Mapping[str, str] | None = None) -> PickResult:
    """Ask the user for a duration; duration None without failure is a cancel."""
    if which(PICKER_COMMAND) is None:
        return PickResult(FALLBACK_DURATION)
    if which(SHELL_COMMAND) is not None:
        ok, why = _shell_responds(run, os.environ if environ is None else environ)
        if not ok:
            return _failure("shell-unresponsive",
                            f"The Omarchy shell is not responding ({why}).")
    labels = [label for label, _ in PICKER_OPTIONS]
    argv = [PICKER_COMMAND, PICKER_PROMPT, *labels, "--", "--width", "360"]
    try:
        result = run(argv, capture_output=True, text=True,
                     timeout=PICKER_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return _failure(
            "timeout",
            f"The duration menu did not answer within {PICKER_TIMEOUT_SECONDS} seconds.")
    except OSError as exc:
        return _failure("os-error", f"The duration menu could not be started: {exc}")
    stderr = result.stderr or ""
    if result.returncode == 1 and not stderr.strip():
        return PickResult(None)
    if result.returncode == 1:
        return _failure("stderr", "The duration menu exited with an error message.",
                        1, stderr)
    if result.returncode != 0:
        return _failure(
            "exit-code",
            f"The duration menu exited with code {result.returncode}.",
            result.returncode, stderr)
    lines = result.stdout.strip().splitlines()
    choice = lines[0].strip() if lines else ""
    duration = dict(PICKER_OPTIONS).get(choice)
    if duration is None:
        return _failure("unknown-choice",
                        f"The duration menu returned an unknown choice: {choice!r}.",
                        0, stderr)
    return PickResult(duration)


def notify(message: str, *, popen=subprocess.Popen) -> None:
    try:
        popen(["notify-send", "-u", "normal", "omarchy-clean", message])
    except OSError:
        pass


def resolve_duration(
    value: str | None,
    pick: Callable[[], PickResult] = pick_duration,
    notify: Callable[[str], None] = notify,
    on_failure: Callable[[PickFailure], None] | None = None,
) -> tuple[int, bool] | None:
    """Parse an explicit duration, or ask the picker; None means cancelled.

    A picker failure is logged and notified. It locks for the fallback duration
    unless the menu may have been shown (the result has no duration).
    """
    if value is None:
        result = pick()
        if result.failure is not None:
            if on_failure is not None:
                on_failure(result.failure)
            notify(NOTIFY_MESSAGE if result.duration is not None
                   else NOTIFY_NO_LOCK_MESSAGE)
        if result.duration is None:
            return None
        value = result.duration
    return parse_duration_arg(value)
