import os
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BEGIN = "-- >>> omarchy-clean >>>"
END = "-- <<< omarchy-clean <<<"
ORIGINAL = 'local o = require("omarchy")\no.bind("SUPER + T", "Terminal", "xdg-terminal")\n'


class InstallScriptTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.home = self.tmp / "home"
        self.hypr = self.home / ".config" / "hypr"
        self.apps = self.home / ".local" / "share" / "applications"
        self.hypr.mkdir(parents=True)
        self.bindings = self.hypr / "bindings.lua"
        self.bindings.write_text(ORIGINAL)
        self.log = self.tmp / "calls.log"
        stubs = self.tmp / "stubs"
        stubs.mkdir()
        for name in ("systemctl", "hyprctl"):
            self._stub(stubs / name, f'echo "{name} $*" >> "{self.log}"\n')
        self._stub(stubs / "sudo", f'echo "sudo $*" >> "{self.log}"\nexit 1\n')
        self.env = dict(
            os.environ,
            HOME=str(self.home),
            HYPR_CONFIG_DIR=str(self.hypr),
            APPS_DIR=str(self.apps),
            PATH=f"{stubs}:{os.environ['PATH']}",
        )

    @staticmethod
    def _stub(path, body):
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def run_script(self, name, *args):
        return subprocess.run(["bash", str(ROOT / name), *args], env=self.env,
                              capture_output=True, text=True)

    def calls(self):
        return self.log.read_text() if self.log.exists() else ""

    def test_install_appends_block_once(self):
        for _ in range(2):
            result = self.run_script("install.sh", "--user-only")
            self.assertEqual(result.returncode, 0, result.stderr)
        text = self.bindings.read_text()
        self.assertTrue(text.startswith(ORIGINAL))
        self.assertEqual(text.count(BEGIN), 1)
        self.assertEqual(text.count(END), 1)
        self.assertIn('o.bind("SUPER + SHIFT + K", "Clean keyboard", "omarchy-clean 60")', text)

    def test_install_writes_desktop_file_and_enables_agent(self):
        self.run_script("install.sh", "--user-only")
        desktop = (self.apps / "omarchy-clean.desktop").read_text()
        for line in ("Name=Clean Keyboard", "Exec=omarchy-clean 60",
                     "Icon=input-keyboard", "Categories=Utility;"):
            self.assertIn(line, desktop)
        self.assertIn("systemctl --user enable --now hyprpolkitagent.service", self.calls())
        self.assertIn("hyprctl reload", self.calls())

    def test_install_creates_missing_bindings(self):
        self.bindings.unlink()
        self.run_script("install.sh", "--user-only")
        self.assertIn(BEGIN, self.bindings.read_text())

    def test_no_keybind_leaves_bindings_alone(self):
        self.run_script("install.sh", "--user-only", "--no-keybind")
        self.assertEqual(self.bindings.read_text(), ORIGINAL)

    def test_uninstall_restores_bindings_byte_identical(self):
        self.run_script("install.sh", "--user-only")
        result = self.run_script("uninstall.sh", "--user-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.bindings.read_bytes(), ORIGINAL.encode())
        self.assertFalse((self.apps / "omarchy-clean.desktop").exists())

    def _assert_refused(self, script, content):
        self.bindings.write_text(content)
        desktop = self.apps / "omarchy-clean.desktop"
        self.apps.mkdir(parents=True)
        desktop.write_text("sentinel")
        result = self.run_script(script, "--user-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bindings.lua", result.stderr)
        self.assertEqual(self.bindings.read_bytes(), content.encode())
        self.assertEqual(desktop.read_text(), "sentinel")
        self.assertNotIn("hyprctl", self.calls())

    def _bad_states(self):
        block = f"{BEGIN}\no.bind()\n{END}\n"
        return {
            "start_without_end": f"{ORIGINAL}{BEGIN}\no.bind()\ntrailing = 1\n",
            "end_without_start": f"{ORIGINAL}{END}\n",
            "end_before_start": f"{ORIGINAL}{END}\n{BEGIN}\n",
            "two_blocks": f"{ORIGINAL}{block}{block}",
        }

    def test_install_refuses_invalid_markers(self):
        for name, content in self._bad_states().items():
            with self.subTest(name):
                self.setUp()
                self._assert_refused("install.sh", content)

    def test_uninstall_refuses_invalid_markers(self):
        for name, content in self._bad_states().items():
            with self.subTest(name):
                self.setUp()
                self._assert_refused("uninstall.sh", content)

    def test_user_only_never_calls_sudo(self):
        self.run_script("install.sh", "--user-only")
        self.run_script("uninstall.sh", "--user-only")
        self.assertNotIn("sudo", self.calls())

    def test_refuses_root(self):
        if os.geteuid() != 0:
            self.skipTest("only meaningful as root")
        self.assertNotEqual(self.run_script("install.sh", "--user-only").returncode, 0)


class PolicyTest(unittest.TestCase):
    def test_policy_parses_and_names_helper(self):
        tree = ET.parse(ROOT / "packaging" / "dev.omarchy.clean.policy")
        action = tree.getroot().find("action")
        self.assertEqual(action.get("id"), "dev.omarchy.clean.helper")
        annotate = {a.get("key"): a.text for a in action.findall("annotate")}
        self.assertEqual(annotate["org.freedesktop.policykit.exec.path"],
                         "/usr/local/lib/omarchy-clean/bin/omarchy-clean-helper")


if __name__ == "__main__":
    unittest.main()
