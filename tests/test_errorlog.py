import json
import os
import stat
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from omarchy_clean import __version__, errorlog
from omarchy_clean.picker import PickFailure

NOW = datetime(2026, 10, 4, 12, 30, 5, tzinfo=timezone.utc)
FAILURE = PickFailure("exit-code", 3, "boom", "The duration menu exited with code 3.")


def fake_run(stdout="Omarchy 4.0\n", returncode=0):
    return lambda *a, **kw: SimpleNamespace(stdout=stdout, returncode=returncode)


def raising_run(exc):
    def run(*a, **kw):
        raise exc
    return run


class StateDirTests(unittest.TestCase):
    def test_uses_xdg_state_home(self):
        env = {"XDG_STATE_HOME": "/tmp/state", "HOME": "/home/x"}
        self.assertEqual(errorlog.state_dir(env), "/tmp/state/omarchy-clean")
        self.assertEqual(errorlog.log_path(env), "/tmp/state/omarchy-clean/last-error.log")

    def test_falls_back_when_unset_empty_or_relative(self):
        expected = "/home/x/.local/state/omarchy-clean"
        for env in ({"HOME": "/home/x"},
                    {"HOME": "/home/x", "XDG_STATE_HOME": ""},
                    {"HOME": "/home/x", "XDG_STATE_HOME": "relative/dir"}):
            self.assertEqual(errorlog.state_dir(env), expected)


class BuildRecordTests(unittest.TestCase):
    def test_exact_keys_and_values(self):
        record = errorlog.build_record(
            FAILURE, now=NOW, omarchy_version="Omarchy 4.0", app_version="0.1.0")
        self.assertEqual(record, {
            "timestamp": "2026-10-04T12:30:05+00:00",
            "reason": "exit-code",
            "detail": FAILURE.detail,
            "returncode": 3,
            "stderr": "boom",
            "omarchy_version": "Omarchy 4.0",
            "omarchy_clean_version": "0.1.0",
        })


class OmarchyVersionTests(unittest.TestCase):
    def test_returns_stripped_stdout(self):
        self.assertEqual(errorlog.omarchy_version(fake_run()), "Omarchy 4.0")

    def test_unknown_on_errors(self):
        for run in (raising_run(OSError("nope")),
                    raising_run(subprocess.TimeoutExpired("omarchy-version", 2)),
                    fake_run(returncode=1),
                    fake_run(stdout="  \n")):
            self.assertEqual(errorlog.omarchy_version(run), "unknown")


class WriteReadTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.env = {"XDG_STATE_HOME": os.path.join(self.tmp, "state"), "HOME": self.tmp}

    def write(self, failure=FAILURE, **kw):
        return errorlog.write_last_error(
            failure, environ=self.env, now=NOW, run=fake_run(), **kw)

    def test_round_trip(self):
        path = self.write()
        self.assertEqual(path, errorlog.log_path(self.env))
        record = errorlog.read_last_error(self.env)
        self.assertEqual(record["reason"], "exit-code")
        self.assertEqual(record["omarchy_version"], "Omarchy 4.0")
        self.assertEqual(record["omarchy_clean_version"], __version__)
        self.assertEqual(record["timestamp"], "2026-10-04T12:30:05+00:00")

    def test_file_format(self):
        text = open(self.write()).read()
        self.assertTrue(text.endswith("}\n"))
        data = json.loads(text)
        self.assertEqual(text, json.dumps(data, indent=2, sort_keys=True) + "\n")

    def test_overwrites_previous(self):
        self.write()
        self.write(PickFailure("timeout", None, "", "slow"))
        record = errorlog.read_last_error(self.env)
        self.assertEqual(record["reason"], "timeout")
        self.assertIsNone(record["returncode"])
        self.assertEqual(os.listdir(errorlog.state_dir(self.env)), [errorlog.LOG_NAME])

    def test_modes(self):
        path = self.write()
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode), 0o700)

    def test_write_failure_returns_none(self):
        blocker = os.path.join(self.tmp, "file")
        open(blocker, "w").close()
        env = {"XDG_STATE_HOME": os.path.join(blocker, "sub"), "HOME": self.tmp}
        self.assertIsNone(errorlog.write_last_error(
            FAILURE, environ=env, now=NOW, run=fake_run()))

    def test_read_missing_and_garbage(self):
        self.assertIsNone(errorlog.read_last_error(self.env))
        os.makedirs(errorlog.state_dir(self.env))
        path = errorlog.log_path(self.env)
        for content in ("not json", "[1, 2]", ""):
            with open(path, "w") as f:
                f.write(content)
            self.assertIsNone(errorlog.read_last_error(self.env))


if __name__ == "__main__":
    unittest.main()
