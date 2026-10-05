"""Local record of the last duration-picker failure (no GTK, nothing personal)."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Mapping
from datetime import datetime, timezone

from omarchy_clean import __version__

LOG_NAME = "last-error.log"
VERSION_COMMAND = "omarchy-version"
VERSION_TIMEOUT_SECONDS = 2


def state_dir(environ: Mapping[str, str] = os.environ) -> str:
    base = environ.get("XDG_STATE_HOME", "")
    if not base or not os.path.isabs(base):
        home = environ.get("HOME") or os.path.expanduser("~")
        base = os.path.join(home, ".local", "state")
    return os.path.join(base, "omarchy-clean")


def log_path(environ: Mapping[str, str] = os.environ) -> str:
    return os.path.join(state_dir(environ), LOG_NAME)


def build_record(failure, *, now: datetime, omarchy_version: str, app_version: str) -> dict:
    return {
        "timestamp": now.astimezone(timezone.utc).isoformat(),
        "reason": failure.reason,
        "detail": failure.detail,
        "returncode": failure.returncode,
        "stderr": failure.stderr,
        "omarchy_version": omarchy_version,
        "omarchy_clean_version": app_version,
    }


def omarchy_version(run=subprocess.run) -> str:
    try:
        result = run([VERSION_COMMAND], capture_output=True, text=True,
                     timeout=VERSION_TIMEOUT_SECONDS)
        if result.returncode != 0:
            return "unknown"
        return (result.stdout or "").strip() or "unknown"
    except Exception:
        return "unknown"


def write_last_error(failure, *, environ: Mapping[str, str] = os.environ,
                     now: datetime | None = None, run=subprocess.run) -> str | None:
    """Persist the failure; returns the log path, or None if it could not be written."""
    tmp_name = None
    try:
        record = build_record(
            failure,
            now=now or datetime.now(timezone.utc),
            omarchy_version=omarchy_version(run),
            app_version=__version__,
        )
        directory = state_dir(environ)
        os.makedirs(directory, mode=0o700, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=".last-error-")
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
        os.chmod(tmp_name, 0o600)
        path = os.path.join(directory, LOG_NAME)
        os.replace(tmp_name, path)
        return path
    except (OSError, ValueError):
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
        return None


def read_last_error(environ: Mapping[str, str] = os.environ) -> dict | None:
    try:
        with open(log_path(environ), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
