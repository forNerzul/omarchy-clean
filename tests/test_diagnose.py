import io
import os
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from omarchy_clean import diagnose, paths
from omarchy_clean.diagnose import Check

ALL_BINS = {"omarchy-menu-select", "omarchy-shell", "notify-send", "pkexec"}
POLICY = "/usr/share/polkit-1/actions/dev.omarchy.clean.policy"
LAYER = "/usr/lib/libgtk4-layer-shell.so"


def make_which(present=ALL_BINS):
    return lambda name: f"/usr/bin/{name}" if name in present else None


def ok_run(*a, **kw):
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def make_exists(missing=()):
    return lambda path: path not in missing


def ok_import(name):
    return object()


def checks(**overrides):
    kw = dict(which=make_which(), run=ok_run, environ={}, exists=make_exists(),
              importer=ok_import)
    kw.update(overrides)
    return {c.name: c for c in diagnose.run_checks(**kw)}


def failing(**overrides):
    return [c for c in checks(**overrides).values() if not c.ok]


RECORD = {
    "timestamp": "2026-10-04T12:30:05+00:00",
    "reason": "exit-code",
    "detail": "The duration menu exited with code 3.",
    "returncode": 3,
    "stderr": "boom happened",
    "omarchy_version": "4.0",
    "omarchy_clean_version": "0.3",
}


NOW = datetime(2026, 10, 4, 12, 30, 5, tzinfo=timezone.utc)


class DescribeAgeTest(unittest.TestCase):
    def age(self, delta=None, timestamp=None):
        if timestamp is None:
            timestamp = (NOW - delta).isoformat()
        return diagnose.describe_age(timestamp, NOW)

    def test_table(self):
        table = [
            (timedelta(seconds=0), "just now"),
            (timedelta(seconds=59), "just now"),
            (timedelta(seconds=60), "1 minute ago"),
            (timedelta(minutes=5), "5 minutes ago"),
            (timedelta(minutes=59, seconds=59), "59 minutes ago"),
            (timedelta(hours=1), "1 hour ago"),
            (timedelta(hours=3, minutes=40), "3 hours ago"),
            (timedelta(hours=23, minutes=59), "23 hours ago"),
            (timedelta(hours=24), "1 day ago"),
            (timedelta(days=4, hours=2), "4 days ago"),
            (timedelta(seconds=-30), "just now"),
        ]
        for delta, expected in table:
            self.assertEqual(self.age(delta), expected, delta)

    def test_none_for_bad_input(self):
        for bad in (None, "", "garbage", "2026-13-99"):
            self.assertIsNone(diagnose.describe_age(bad, NOW), bad)
        self.assertIsNone(self.age(timedelta(seconds=-61)))

    def test_naive_is_utc(self):
        self.assertEqual(self.age(timestamp="2026-10-04T09:30:05"), "3 hours ago")

    def test_other_offset(self):
        self.assertEqual(self.age(timestamp="2026-10-04T07:30:05-04:00"),
                         "1 hour ago")


class RunChecksTest(unittest.TestCase):
    def test_all_ok(self):
        result = checks()
        self.assertEqual(len(result), 8)
        self.assertTrue(all(c.ok and c.fix is None for c in result.values()))

    def test_menu_select_missing(self):
        bad = failing(which=make_which(ALL_BINS - {"omarchy-menu-select"}))
        self.assertEqual(len(bad), 1)
        self.assertIn("omarchy-menu-select", bad[0].name)
        self.assertEqual(
            bad[0].fix,
            "Update Omarchy; without it omarchy-clean always locks for 1 minute.")

    def test_shell_ping_ok_uses_short_timeout(self):
        calls = []

        def run(argv, **kw):
            calls.append((argv, kw))
            return ok_run()

        checks(run=run, environ={"HOME": "/h"})
        argv, kw = calls[0]
        self.assertEqual(argv, ["omarchy-shell", "shell", "ping"])
        self.assertEqual(kw["env"]["OMARCHY_SHELL_IPC_TIMEOUT"], "0.5s")
        self.assertEqual(kw["env"]["HOME"], "/h")
        self.assertEqual(kw["timeout"], 3)

    def test_shell_ping_failures(self):
        def bad_code(*a, **kw):
            return SimpleNamespace(returncode=2, stdout="", stderr="")

        def timeout(*a, **kw):
            raise subprocess.TimeoutExpired("x", 3)

        def oserror(*a, **kw):
            raise OSError("nope")

        for run in (bad_code, timeout, oserror):
            bad = failing(run=run)
            self.assertEqual(len(bad), 1)
            self.assertIn("shell", bad[0].name)
            self.assertEqual(bad[0].fix, "Run: omarchy-restart-shell")

    def test_shell_binary_missing_fails_ping(self):
        bad = failing(which=make_which(ALL_BINS - {"omarchy-shell"}))
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0].fix, "Run: omarchy-restart-shell")

    def test_notify_send_missing(self):
        bad = failing(which=make_which(ALL_BINS - {"notify-send"}))
        self.assertEqual(len(bad), 1)
        self.assertIn("libnotify", bad[0].fix)

    def test_pkexec_missing(self):
        bad = failing(which=make_which(ALL_BINS - {"pkexec"}))
        self.assertEqual(len(bad), 1)
        self.assertIn("polkit", bad[0].fix)

    def test_helper_missing(self):
        bad = failing(exists=make_exists({paths.default_helper_path()}))
        self.assertEqual(len(bad), 1)
        self.assertIn("helper", bad[0].name)
        self.assertIn("Reinstall omarchy-clean", bad[0].fix)

    def test_policy_missing(self):
        bad = failing(exists=make_exists({POLICY}))
        self.assertEqual(len(bad), 1)
        self.assertIn("olkit", bad[0].name)
        self.assertIn("Reinstall omarchy-clean", bad[0].fix)

    def test_evdev_missing(self):
        def importer(name):
            raise ImportError(name)

        bad = failing(importer=importer)
        self.assertEqual(len(bad), 1)
        self.assertIn("evdev", bad[0].name)
        self.assertIn("python-evdev", bad[0].fix)

    def test_evdev_import_asks_for_evdev(self):
        seen = []
        checks(importer=lambda name: seen.append(name))
        self.assertEqual(seen, ["evdev"])

    def test_layer_shell_missing(self):
        bad = failing(exists=make_exists({LAYER}))
        self.assertEqual(len(bad), 1)
        self.assertIn("gtk4-layer-shell", bad[0].fix)


class ExplainErrorTest(unittest.TestCase):
    def explain(self, reason, **extra):
        return diagnose.explain_error({**RECORD, "reason": reason, **extra})

    def test_each_reason(self):
        expectations = {
            "shell-unresponsive": "omarchy-restart-shell",
            "timeout": "omarchy-restart-shell",
            "exit-code": "code 3",
            "stderr": "boom happened",
            "unknown-choice": "Update",
            "os-error": "could not be started",
        }
        seen = set()
        for reason, needle in expectations.items():
            text = self.explain(reason)
            self.assertIn(needle, text, reason)
            self.assertIn("Next step", text, reason)
            seen.add(text)
        self.assertEqual(len(seen), len(expectations))

    def test_unknown_reason_falls_back(self):
        text = self.explain("something-new")
        self.assertIn("something-new", text)
        self.assertIn("Next step", text)

    def test_empty_record_does_not_crash(self):
        self.assertIn("Next step", diagnose.explain_error({}))


class BuildReportTest(unittest.TestCase):
    def report(self, last_error):
        return diagnose.build_report(
            [
                Check("pkexec", True, "found", None),
                Check("shell", False, "no answer", "Run: omarchy-restart-shell"),
            ],
            last_error, app_version="0.3", omarchy_version="4.0")

    def test_versions_checks_and_error(self):
        text = self.report(RECORD)
        self.assertIn("0.3", text)
        self.assertIn("4.0", text)
        self.assertIn("- [ok] pkexec", text)
        self.assertIn("- [FAIL] shell", text)
        self.assertIn("Run: omarchy-restart-shell", text)
        self.assertIn("2026-10-04T12:30:05+00:00", text)
        self.assertIn("exit-code", text)
        self.assertIn("The duration menu exited with code 3.", text)
        self.assertIn("boom happened", text)
        self.assertIn("```", text)

    def test_old_unscrubbed_record_is_scrubbed(self):
        old = dict(RECORD, stderr="cannot open /home/alice/x",
                   detail="in /home/alice/y")
        text = diagnose.build_report([], old, app_version="0.3", omarchy_version="4.0",
                                     environ={"HOME": "/home/alice"})
        self.assertNotIn("alice", text)
        self.assertIn("cannot open ~/x", text)
        self.assertIn("in ~/y", text)

    def test_when_line_with_age(self):
        text = diagnose.build_report([], RECORD, app_version="0.3",
                                     omarchy_version="4.0", now=NOW)
        self.assertIn("- Time: 2026-10-04T12:30:05+00:00\n- When: just now", text)

    def test_no_when_line_without_age(self):
        text = self.report(dict(RECORD, timestamp="garbage"))
        self.assertNotIn("When:", text)

    def test_no_error(self):
        text = self.report(None)
        self.assertIn("No error recorded.", text)
        self.assertNotIn("```", text)


class MainTest(unittest.TestCase):
    def run_main(self, last_error=None, **overrides):
        out = io.StringIO()
        kw = dict(which=make_which(), run=ok_run, environ={},
                  exists=make_exists(), importer=ok_import,
                  read_last_error=lambda: last_error, now=NOW)
        kw.update(overrides)
        code = diagnose.main([], out=out, **kw)
        return code, out.getvalue()

    def test_all_clear_prints_no_report(self):
        code, text = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("omarchy-clean diagnostics", text)
        self.assertIn("- [ok] pkexec", text)
        self.assertIn("Everything looks fine. Nothing to report.", text)
        for absent in ("To report it", diagnose.ISSUES_URL, "BEGIN", "END",
                       "Home folder paths", "Last error"):
            self.assertNotIn(absent, text)

    def test_failed_check_without_error_shows_report(self):
        code, text = self.run_main(which=make_which(ALL_BINS - {"pkexec"}))
        self.assertEqual(code, 1)
        self.assertNotIn("Everything looks fine", text)
        self.assertIn("No error recorded since install.", text)
        self.assertIn("To report it:", text)
        self.assertIn(diagnose.BEGIN_MARKER, text)
        self.assertIn(diagnose.END_MARKER, text)
        self.assertIn(diagnose.PRIVACY_NOTE, text)

    def test_error_with_all_ok_shows_report_and_age(self):
        code, text = self.run_main(
            last_error=dict(RECORD, timestamp=(NOW - timedelta(days=3)).isoformat()),
            now=NOW)
        self.assertEqual(code, 0)
        self.assertNotIn("Everything looks fine", text)
        self.assertIn("Last error (3 days ago)", text)
        self.assertIn("- When: 3 days ago", text)
        self.assertIn("To report it:", text)
        self.assertIn(diagnose.BEGIN_MARKER, text)
        self.assertIn(diagnose.PRIVACY_NOTE, text)
        self.assertNotIn("no personal data", text)

    def test_unknown_age_heading_is_plain(self):
        _, text = self.run_main(last_error=dict(RECORD, timestamp="garbage"), now=NOW)
        self.assertIn("\nLast error\n", text)
        self.assertNotIn("Last error (", text)

    def test_old_record_scrubbed_in_explanation_and_report(self):
        old = dict(RECORD, reason="stderr", stderr="bad /home/alice/x")
        _, text = self.run_main(last_error=old, environ={"HOME": "/home/alice"},
                                now=NOW)
        self.assertNotIn("alice", text)
        self.assertEqual(text.count("bad ~/x"), 2)

    def test_issues_url(self):
        self.assertEqual(diagnose.ISSUES_URL,
                         "https://github.com/forNerzul/omarchy-clean/issues")

    def test_failure_exit_one_with_fix(self):
        code, text = self.run_main(which=make_which(ALL_BINS - {"pkexec"}))
        self.assertEqual(code, 1)
        self.assertIn("polkit", text)

    def test_section_order(self):
        _, text = self.run_main(last_error=RECORD, now=NOW)
        self.assertIn("boom happened", text)
        order = [text.index(s) for s in
                 ("Last error", "To report it:", diagnose.ISSUES_URL, "BEGIN",
                  "END", "Home folder paths")]
        self.assertEqual(order, sorted(order))
        self.assertLess(text.index("pkexec"), text.index("Last error"))


class BinScriptTest(unittest.TestCase):
    def test_diagnose_handled_before_ld_preload_and_overlay(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "bin", "omarchy-clean"), encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("--diagnose", source)
        diag = source.index("--diagnose")
        self.assertLess(diag, source.index("LD_PRELOAD"))
        self.assertLess(diag, source.index("import overlay"))
        self.assertLess(source.index("sys.path.insert"), diag)


if __name__ == "__main__":
    unittest.main()
