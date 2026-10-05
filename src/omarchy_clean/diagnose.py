"""`omarchy-clean --diagnose`: check the setup and build a shareable report (no GTK)."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from omarchy_clean import __version__, errorlog
from omarchy_clean.paths import default_helper_path
from omarchy_clean.picker import PICKER_COMMAND, SHELL_COMMAND, _shell_responds

ISSUES_URL = "https://github.com/forNerzul/omarchy-clean/issues"
POLICY_PATH = "/usr/share/polkit-1/actions/dev.omarchy.clean.policy"
LAYER_SHELL_PATH = "/usr/lib/libgtk4-layer-shell.so"
REINSTALL_FIX = "Reinstall omarchy-clean (omarchy-clean-setup or the AUR package)."
RESTART_SHELL_FIX = "Run: omarchy-restart-shell"
PRIVACY_NOTE = (
    "This report contains no personal data. Review it before sharing; "
    "omarchy-clean never sends anything on its own."
)
BEGIN_MARKER = "----- BEGIN REPORT -----"
END_MARKER = "----- END REPORT -----"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    fix: str | None = None


def _check(name: str, ok: bool, good: str, bad: str, fix: str) -> Check:
    return Check(name, ok, good if ok else bad, None if ok else fix)


def run_checks(*, which=shutil.which, run=subprocess.run,
               environ: Mapping[str, str] | None = None,
               exists: Callable[[str], bool] = os.path.exists,
               importer: Callable[[str], object] = importlib.import_module,
               ) -> list[Check]:
    environ = os.environ if environ is None else environ
    results = [
        _check(PICKER_COMMAND, which(PICKER_COMMAND) is not None,
               "found", "not found",
               "Update Omarchy; without it omarchy-clean always locks for 1 minute."),
    ]
    if which(SHELL_COMMAND) is None:
        results.append(Check("omarchy-shell responds", False,
                             "omarchy-shell not found", RESTART_SHELL_FIX))
    else:
        ok, why = _shell_responds(run, environ)
        results.append(_check("omarchy-shell responds", ok, "answered the ping",
                              why, RESTART_SHELL_FIX))
    results.append(_check("notify-send", which("notify-send") is not None,
                          "found", "not found", "Install libnotify."))
    results.append(_check("pkexec", which("pkexec") is not None,
                          "found", "not found", "Install polkit."))
    helper = default_helper_path()
    results.append(_check("helper", bool(exists(helper)), helper,
                          f"missing: {helper}", REINSTALL_FIX))
    results.append(_check("polkit policy", bool(exists(POLICY_PATH)), POLICY_PATH,
                          f"missing: {POLICY_PATH}", REINSTALL_FIX))
    try:
        importer("evdev")
        evdev_ok = True
    except ImportError:
        evdev_ok = False
    results.append(_check("python evdev", evdev_ok, "importable", "not importable",
                          "Install python-evdev."))
    results.append(_check("gtk4-layer-shell", bool(exists(LAYER_SHELL_PATH)),
                          LAYER_SHELL_PATH, f"missing: {LAYER_SHELL_PATH}",
                          "Install gtk4-layer-shell."))
    return results


def explain_error(record: dict) -> str:
    reason = record.get("reason")
    if reason == "shell-unresponsive":
        what = "The Omarchy shell did not answer, so the menu could not open."
        step = "Run omarchy-restart-shell, then try again."
    elif reason == "timeout":
        what = "The duration menu opened but never answered."
        step = "Run omarchy-restart-shell, then try again."
    elif reason == "exit-code":
        what = (f"The duration menu stopped with code {record.get('returncode')}.")
        step = "Update Omarchy, then try again. If it keeps happening, report it."
    elif reason == "stderr":
        what = ("The duration menu printed an error: "
                f"{(record.get('stderr') or '').strip() or 'no message'}")
        step = "Run omarchy-restart-shell and try again. If it persists, report it."
    elif reason == "unknown-choice":
        what = "The menu returned a choice omarchy-clean does not know."
        step = "Update Omarchy and omarchy-clean so they match."
    elif reason == "os-error":
        what = "The duration menu could not be started."
        step = "Check that omarchy-menu-select is installed (update Omarchy)."
    else:
        what = f"Something unexpected happened ({reason or 'no reason recorded'})."
        step = "Try again. If it keeps happening, report it."
    return f"{what}\nNext step: {step}"


def _format_check(check: Check) -> str:
    if check.ok:
        return f"- [ok] {check.name}"
    line = f"- [FAIL] {check.name}"
    if check.detail:
        line += f" ({check.detail})"
    if check.fix:
        line += f" — {check.fix}"
    return line


def build_report(checks: list[Check], last_error: dict | None, *,
                 app_version: str, omarchy_version: str) -> str:
    lines = [
        "### omarchy-clean report",
        "",
        f"- omarchy-clean: {app_version}",
        f"- Omarchy: {omarchy_version}",
        "",
        "#### Checks",
        *(_format_check(c) for c in checks),
        "",
        "#### Last error",
    ]
    if last_error is None:
        lines.append("No error recorded.")
    else:
        for label, key in (("Time", "timestamp"), ("Reason", "reason"),
                           ("Detail", "detail"), ("Exit code", "returncode")):
            lines.append(f"- {label}: {last_error.get(key)}")
        lines += ["- Error output:", "```", str(last_error.get("stderr") or ""), "```"]
    return "\n".join(lines)


def main(argv=None, *, out=sys.stdout, which=shutil.which, run=subprocess.run,
         environ: Mapping[str, str] | None = None,
         exists: Callable[[str], bool] = os.path.exists,
         importer: Callable[[str], object] = importlib.import_module,
         read_last_error: Callable[[], dict | None] | None = None) -> int:
    environ = os.environ if environ is None else environ
    if read_last_error is None:
        def read_last_error():
            return errorlog.read_last_error(environ)
    checks = run_checks(which=which, run=run, environ=environ, exists=exists,
                        importer=importer)
    last_error = read_last_error()

    def say(text=""):
        print(text, file=out)

    say("omarchy-clean diagnostics")
    say()
    for check in checks:
        say(_format_check(check))
    say()
    say("Last error")
    if last_error is None:
        say("No error recorded since install.")
    else:
        say(explain_error(last_error))
    say()
    say("To report it:")
    say(f"Open an issue at {ISSUES_URL} and paste this report:")
    say(BEGIN_MARKER)
    say(build_report(checks, last_error, app_version=__version__,
                     omarchy_version=errorlog.omarchy_version(run)))
    say(END_MARKER)
    say(PRIVACY_NOTE)
    return 0 if all(c.ok for c in checks) else 1
