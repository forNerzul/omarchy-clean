import re
import shutil
import subprocess
import unittest
from pathlib import Path

from omarchy_clean import __version__

ROOT = Path(__file__).resolve().parent.parent
AUR = ROOT / "packaging" / "aur"


class PackagingTests(unittest.TestCase):
    def test_pkgver_matches_package_version(self):
        text = (AUR / "PKGBUILD").read_text()
        match = re.search(r"^pkgver=(\S+)$", text, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), __version__)

    @unittest.skipUnless(shutil.which("makepkg"), "makepkg not available")
    def test_srcinfo_in_sync(self):
        out = subprocess.run(
            ["makepkg", "--printsrcinfo"],
            cwd=AUR, capture_output=True, text=True, check=True,
        ).stdout
        self.assertEqual((AUR / ".SRCINFO").read_text(), out)

    def test_license_is_mit_with_holder(self):
        text = (ROOT / "LICENSE").read_text()
        self.assertIn("MIT License", text)
        self.assertIn("Sergio Javier Garcia Martinez", text)


if __name__ == "__main__":
    unittest.main()
