import os
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class WrapperTest(unittest.TestCase):
    """install.sh / uninstall.sh are thin wrappers; setup and make are stubbed."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.log = self.tmp / "calls.log"
        stubs = self.tmp / "stubs"
        stubs.mkdir()
        for name in ("sudo", "pacman"):
            self._stub(stubs / name, f'echo "{name} $*" >> "{self.log}"\n')
        self._stub(stubs / "systemctl", "exit 0\n")
        self._stub(stubs / "hyprctl", "exit 0\n")
        self.home = self.tmp / "home"
        (self.home / ".config" / "hypr").mkdir(parents=True)
        self.env = dict(
            os.environ,
            HOME=str(self.home),
            HYPR_CONFIG_DIR=str(self.home / ".config" / "hypr"),
            APPS_DIR=str(self.home / "apps"),
            PATH=f"{stubs}:{os.environ['PATH']}",
        )
        self.env.pop("PREFIX", None)

    @staticmethod
    def _stub(path, body):
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def run_script(self, name, *args):
        return subprocess.run(["bash", str(ROOT / name), *args], env=self.env,
                              capture_output=True, text=True)

    def calls(self):
        return self.log.read_text() if self.log.exists() else ""

    def bindings(self):
        return (self.home / ".config" / "hypr" / "bindings.lua").read_text()

    def test_install_user_only_runs_setup_without_sudo(self):
        result = self.run_script("install.sh", "--user-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("omarchy-clean", self.bindings())
        self.assertNotIn("sudo", self.calls())

    def test_install_passes_no_keybind_through(self):
        self.run_script("install.sh", "--user-only", "--no-keybind")
        self.assertFalse((self.home / ".config" / "hypr" / "bindings.lua").exists())

    def test_install_runs_make_via_sudo(self):
        self.env["PREFIX"] = "/usr"
        result = self.run_script("install.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"sudo make -C {ROOT} install PREFIX=/usr", self.calls())

    def test_install_default_prefix(self):
        self.run_script("install.sh")
        self.assertIn(f"sudo make -C {ROOT} install PREFIX=/usr/local", self.calls())

    def test_install_missing_packages_prints_pacman_command(self):
        self._stub(self.tmp / "stubs" / "pacman", "exit 1\n")
        result = self.run_script("install.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sudo pacman -S", result.stderr)
        self.assertNotIn("sudo make", self.calls())

    def test_uninstall_removes_block_then_runs_make_uninstall(self):
        self.run_script("install.sh", "--user-only")
        result = self.run_script("uninstall.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("omarchy-clean", self.bindings())
        self.assertIn(f"sudo make -C {ROOT} uninstall PREFIX=/usr/local", self.calls())

    def test_uninstall_user_only_never_calls_sudo(self):
        self.run_script("uninstall.sh", "--user-only")
        self.assertNotIn("sudo", self.calls())

    def test_refuses_root(self):
        if os.geteuid() != 0:
            self.skipTest("only meaningful as root")
        for name in ("install.sh", "uninstall.sh"):
            self.assertNotEqual(self.run_script(name, "--user-only").returncode, 0)


class PolicyTest(unittest.TestCase):
    def test_policy_template_parses_and_has_placeholder(self):
        tree = ET.parse(ROOT / "packaging" / "dev.omarchy.clean.policy.in")
        action = tree.getroot().find("action")
        self.assertEqual(action.get("id"), "dev.omarchy.clean.helper")
        annotate = {a.get("key"): a.text for a in action.findall("annotate")}
        self.assertEqual(annotate["org.freedesktop.policykit.exec.path"],
                         "@HELPER_PATH@")


if __name__ == "__main__":
    unittest.main()
