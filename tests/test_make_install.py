import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY_MODULES = sorted(p.name for p in (ROOT / "src" / "omarchy_clean").glob("*.py"))


class MakeInstallTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dest = Path(tmp.name) / "pkg"
        self.home = Path(tmp.name) / "home"
        self.home.mkdir()
        self.env = dict(os.environ, HOME=str(self.home))

    def make(self, target):
        return subprocess.run(
            ["make", "-C", str(ROOT), target, f"DESTDIR={self.dest}", "PREFIX=/usr"],
            env=self.env, capture_output=True, text=True)

    def path(self, p):
        return self.dest / p.lstrip("/")

    def mode(self, p):
        return stat.S_IMODE(self.path(p).stat().st_mode)

    def files(self):
        return sorted(str(p.relative_to(self.dest)) for p in self.dest.rglob("*")
                      if p.is_file() or p.is_symlink())

    def test_install_places_files_with_modes(self):
        result = self.make("install")
        self.assertEqual(result.returncode, 0, result.stderr)
        lib = "/usr/lib/omarchy-clean"
        for name in PY_MODULES:
            self.assertEqual(self.mode(f"{lib}/src/omarchy_clean/{name}"), 0o644)
        for exe in (f"{lib}/bin/omarchy-clean", f"{lib}/bin/omarchy-clean-helper",
                    "/usr/bin/omarchy-clean-setup"):
            self.assertEqual(self.mode(exe), 0o755, exe)
        for p in ("/usr/share/applications/omarchy-clean.desktop",
                  "/usr/share/polkit-1/actions/dev.omarchy.clean.policy"):
            self.assertEqual(self.mode(p), 0o644, p)

    def test_symlink_is_relative_and_resolves_inside_destdir(self):
        self.make("install")
        link = self.path("/usr/bin/omarchy-clean")
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), "../lib/omarchy-clean/bin/omarchy-clean")
        self.assertEqual(link.resolve(),
                         self.path("/usr/lib/omarchy-clean/bin/omarchy-clean").resolve())

    def test_policy_rendered_with_final_helper_path(self):
        self.make("install")
        text = self.path("/usr/share/polkit-1/actions/dev.omarchy.clean.policy").read_text()
        self.assertIn(">/usr/lib/omarchy-clean/bin/omarchy-clean-helper<", text)
        self.assertNotIn("@HELPER_PATH@", text)
        self.assertNotIn(str(self.dest), text)

    def test_desktop_file_content(self):
        self.make("install")
        text = self.path("/usr/share/applications/omarchy-clean.desktop").read_text()
        self.assertIn("Exec=omarchy-clean 60", text)

    def test_install_never_touches_home(self):
        self.make("install")
        self.assertEqual(list(self.home.iterdir()), [])

    def test_uninstall_removes_everything_installed(self):
        self.assertEqual(self.make("install").returncode, 0)
        result = self.make("uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.files(), [])
        self.assertFalse(self.path("/usr/lib/omarchy-clean").exists())


if __name__ == "__main__":
    unittest.main()
