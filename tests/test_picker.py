import subprocess
import unittest

from omarchy_clean.overlay_model import parse_duration_arg
from omarchy_clean.picker import (
    FALLBACK_DURATION,
    PICKER_COMMAND,
    PICKER_OPTIONS,
    pick_duration,
    resolve_duration,
)

LABELS = ["30 seconds", "1 minute", "2 minutes", "5 minutes", "No limit (Esc + Enter)"]


def fake_run(stdout="", returncode=0, calls=None, exc=None):
    def run(argv, **kwargs):
        if calls is not None:
            calls.append((argv, kwargs))
        if exc is not None:
            raise exc
        return subprocess.CompletedProcess(argv, returncode, stdout, "")
    return run


def present(_name):
    return "/usr/bin/omarchy-menu-select"


class PickDurationTests(unittest.TestCase):
    def test_missing_command_falls_back_without_running(self):
        calls = []
        result = pick_duration(run=fake_run(calls=calls), which=lambda _n: None)
        self.assertEqual(result, "60")
        self.assertEqual(FALLBACK_DURATION, "60")
        self.assertEqual(calls, [])

    def test_each_label_maps_to_arg(self):
        expected = ["30", "60", "120", "300", "unlimited"]
        for label, arg in zip(LABELS, expected):
            with self.subTest(label=label):
                got = pick_duration(run=fake_run(label + "\n"), which=present)
                self.assertEqual(got, arg)

    def test_exact_argv(self):
        calls = []
        pick_duration(run=fake_run("1 minute\n", calls=calls), which=present)
        argv, kwargs = calls[0]
        self.assertEqual(
            argv,
            [PICKER_COMMAND, "Lock keyboard for", *LABELS, "--", "--width", "360"],
        )
        self.assertTrue(kwargs.get("capture_output"))
        self.assertTrue(kwargs.get("text"))

    def test_cancel_returns_none(self):
        self.assertIsNone(pick_duration(run=fake_run("", returncode=1), which=present))

    def test_unknown_output_returns_none(self):
        self.assertIsNone(pick_duration(run=fake_run("bogus\n"), which=present))

    def test_first_line_used(self):
        got = pick_duration(run=fake_run("5 minutes\nextra\n"), which=present)
        self.assertEqual(got, "300")

    def test_oserror_falls_back(self):
        got = pick_duration(run=fake_run(exc=OSError("boom")), which=present)
        self.assertEqual(got, "60")

    def test_options_accepted_by_parser(self):
        self.assertEqual([label for label, _ in PICKER_OPTIONS], LABELS)
        for _label, arg in PICKER_OPTIONS:
            with self.subTest(arg=arg):
                parse_duration_arg(arg)


class ResolveDurationTests(unittest.TestCase):
    def test_explicit_value_skips_picker(self):
        def pick():
            raise AssertionError("picker must not run")
        self.assertEqual(resolve_duration("60", pick), (60, False))

    def test_picker_unlimited(self):
        self.assertEqual(resolve_duration(None, lambda: "unlimited"),
                         (None, True))

    def test_picker_cancel_returns_none(self):
        self.assertIsNone(resolve_duration(None, lambda: None))


if __name__ == "__main__":
    unittest.main()
