import subprocess
import unittest

from omarchy_clean.overlay_model import parse_duration_arg
from omarchy_clean.picker import (
    FALLBACK_DURATION,
    PICKER_COMMAND,
    PICKER_OPTIONS,
    PICKER_TIMEOUT_SECONDS,
    PING_COMMAND,
    NOTIFY_MESSAGE,
    NOTIFY_NO_LOCK_MESSAGE,
    PickFailure,
    PickResult,
    notify,
    pick_duration,
    resolve_duration,
)

LABELS = ["30 seconds", "1 minute", "2 minutes", "5 minutes", "No limit (Esc + Enter)"]


def fake_run(stdout="", returncode=0, calls=None, exc=None, stderr="",
             ping_code=0, ping_exc=None):
    def run(argv, **kwargs):
        if calls is not None:
            calls.append((argv, kwargs))
        if argv[0] == "omarchy-shell":
            if ping_exc is not None:
                raise ping_exc
            return subprocess.CompletedProcess(argv, ping_code, "", "")
        if exc is not None:
            raise exc
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)
    return run


def present(_name):
    return "/usr/bin/" + _name


def only_menu(name):
    return present(name) if name == PICKER_COMMAND else None


class PickDurationTests(unittest.TestCase):
    def test_missing_command_falls_back_without_running(self):
        calls = []
        result = pick_duration(run=fake_run(calls=calls), which=lambda _n: None)
        self.assertEqual(result, PickResult("60", None))
        self.assertEqual(FALLBACK_DURATION, "60")
        self.assertEqual(calls, [])

    def test_each_label_maps_to_arg(self):
        expected = ["30", "60", "120", "300", "unlimited"]
        for label, arg in zip(LABELS, expected):
            with self.subTest(label=label):
                got = pick_duration(run=fake_run(label + "\n"), which=present)
                self.assertEqual(got, PickResult(arg, None))

    def test_exact_argv_and_timeout(self):
        calls = []
        pick_duration(run=fake_run("1 minute\n", calls=calls), which=present)
        argv, kwargs = calls[-1]
        self.assertEqual(
            argv,
            [PICKER_COMMAND, "Lock keyboard for", *LABELS, "--", "--width", "360"],
        )
        self.assertTrue(kwargs.get("capture_output"))
        self.assertTrue(kwargs.get("text"))
        self.assertEqual(kwargs.get("timeout"), PICKER_TIMEOUT_SECONDS)

    def test_preflight_ping_runs_first_with_short_timeout(self):
        calls = []
        pick_duration(run=fake_run("1 minute\n", calls=calls), which=present,
                      environ={"HOME": "/x"})
        argv, kwargs = calls[0]
        self.assertEqual(argv, PING_COMMAND)
        self.assertEqual(argv, ["omarchy-shell", "shell", "ping"])
        self.assertEqual(kwargs["env"]["OMARCHY_SHELL_IPC_TIMEOUT"], "0.5s")
        self.assertEqual(kwargs["env"]["HOME"], "/x")
        self.assertLessEqual(kwargs["timeout"], 5)
        self.assertEqual(len(calls), 2)

    def test_ping_skipped_when_shell_not_on_path(self):
        calls = []
        got = pick_duration(run=fake_run("1 minute\n", calls=calls), which=only_menu)
        self.assertEqual(got, PickResult("60", None))
        self.assertEqual([c[0][0] for c in calls], [PICKER_COMMAND])

    def test_ping_failure_skips_menu(self):
        for kwargs in ({"ping_code": 1},
                       {"ping_exc": subprocess.TimeoutExpired("p", 3)},
                       {"ping_exc": OSError("x")}):
            with self.subTest(**{k: str(v) for k, v in kwargs.items()}):
                calls = []
                got = pick_duration(run=fake_run("1 minute\n", calls=calls, **kwargs),
                                    which=present)
                self.assertEqual(got.duration, "60")
                self.assertEqual(got.failure.reason, "shell-unresponsive")
                self.assertTrue(got.failure.detail)
                self.assertEqual(len(calls), 1)

    def test_cancel_is_not_a_failure(self):
        got = pick_duration(run=fake_run("", returncode=1), which=present)
        self.assertEqual(got, PickResult(None, None))
        got = pick_duration(run=fake_run("", returncode=1, stderr=" \n"), which=present)
        self.assertEqual(got, PickResult(None, None))

    def test_exit_one_with_stderr_is_failure(self):
        got = pick_duration(run=fake_run("", returncode=1, stderr="boom\n"),
                            which=present)
        self.assertIsNone(got.duration)
        self.assertEqual(got.failure.reason, "stderr")
        self.assertEqual(got.failure.returncode, 1)
        self.assertEqual(got.failure.stderr, "boom\n")

    def test_other_exit_code_is_failure(self):
        got = pick_duration(run=fake_run("", returncode=2), which=present)
        self.assertEqual(got.duration, "60")
        self.assertEqual(got.failure.reason, "exit-code")
        self.assertEqual(got.failure.returncode, 2)

    def test_stderr_truncated(self):
        got = pick_duration(run=fake_run("", returncode=3, stderr="x" * 5000),
                            which=present)
        self.assertLessEqual(len(got.failure.stderr), 2000)

    def test_unknown_or_empty_output_is_failure(self):
        for out in ("bogus\n", ""):
            with self.subTest(out=out):
                got = pick_duration(run=fake_run(out), which=present)
                self.assertEqual(got.duration, "60")
                self.assertEqual(got.failure.reason, "unknown-choice")
                self.assertEqual(got.failure.returncode, 0)

    def test_first_line_used(self):
        got = pick_duration(run=fake_run("5 minutes\nextra\n"), which=present)
        self.assertEqual(got, PickResult("300", None))

    def test_timeout_is_failure(self):
        got = pick_duration(
            run=fake_run(exc=subprocess.TimeoutExpired("m", 120)), which=present)
        self.assertIsNone(got.duration)
        self.assertEqual(got.failure.reason, "timeout")
        self.assertIsNone(got.failure.returncode)

    def test_oserror_is_failure(self):
        got = pick_duration(run=fake_run(exc=OSError("boom")), which=present)
        self.assertEqual(got.duration, "60")
        self.assertEqual(got.failure.reason, "os-error")
        self.assertIn("boom", got.failure.detail)

    def test_options_accepted_by_parser(self):
        self.assertEqual([label for label, _ in PICKER_OPTIONS], LABELS)
        for _label, arg in PICKER_OPTIONS:
            with self.subTest(arg=arg):
                parse_duration_arg(arg)


class NotifyTests(unittest.TestCase):
    def test_runs_notify_send(self):
        calls = []
        notify("hi", popen=lambda argv, **kw: calls.append(argv))
        self.assertEqual(calls, [["notify-send", "-u", "normal", "omarchy-clean", "hi"]])

    def test_swallows_oserror(self):
        def popen(argv, **kw):
            raise OSError("no notify-send")
        notify("hi", popen=popen)


class ResolveDurationTests(unittest.TestCase):
    def test_explicit_value_skips_picker(self):
        def pick():
            raise AssertionError("picker must not run")
        self.assertEqual(resolve_duration("60", pick), (60, False))

    def test_picker_unlimited(self):
        self.assertEqual(resolve_duration(None, lambda: PickResult("unlimited", None)),
                         (None, True))

    def test_picker_cancel_returns_none_quietly(self):
        sent = []
        self.assertIsNone(resolve_duration(None, lambda: PickResult(None, None),
                                           notify=sent.append))
        self.assertEqual(sent, [])

    def test_locking_failure_notifies_and_locks_fallback(self):
        for reason in ("shell-unresponsive", "os-error", "exit-code",
                       "unknown-choice"):
            with self.subTest(reason=reason):
                sent = []
                failure = PickFailure(reason, None, "", "x")
                got = resolve_duration(None, lambda: PickResult("60", failure),
                                       notify=sent.append)
                self.assertEqual(got, (60, False))
                self.assertEqual(sent, [NOTIFY_MESSAGE])
        self.assertEqual(
            NOTIFY_MESSAGE,
            "Could not open the duration menu. Locking for 1 minute. "
            "Details: omarchy-clean --diagnose")

    def test_no_lock_failure_logs_then_notifies_and_returns_none(self):
        for reason in ("timeout", "stderr"):
            with self.subTest(reason=reason):
                events = []
                failure = PickFailure(reason, None, "", "x")
                got = resolve_duration(
                    None, lambda: PickResult(None, failure),
                    notify=lambda m: events.append(("notify", m)),
                    on_failure=lambda f: events.append(("log", f)))
                self.assertIsNone(got)
                self.assertEqual(events, [("log", failure),
                                          ("notify", NOTIFY_NO_LOCK_MESSAGE)])
        self.assertEqual(
            NOTIFY_NO_LOCK_MESSAGE,
            "The duration menu did not finish. Nothing was locked. "
            "Details: omarchy-clean --diagnose")

    def test_failure_hook_receives_failure(self):
        seen = []
        failure = PickFailure("os-error", None, "", "boom")
        resolve_duration(None, lambda: PickResult("60", failure),
                         notify=lambda _m: None, on_failure=seen.append)
        self.assertEqual(seen, [failure])


if __name__ == "__main__":
    unittest.main()
