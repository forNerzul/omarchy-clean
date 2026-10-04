import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from omarchy_clean import paths

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = (ROOT / "packaging" / "dev.omarchy.clean.policy.in").read_text()
EXEC_PATH = "org.freedesktop.policykit.exec.path"


class DefaultHelperPathTest(unittest.TestCase):
    def test_env_override_wins(self):
        env = {"OMARCHY_CLEAN_HELPER": "/custom/helper"}
        self.assertEqual(paths.default_helper_path("/a/src/omarchy_clean/paths.py", env),
                         "/custom/helper")

    def test_empty_env_ignored(self):
        env = {"OMARCHY_CLEAN_HELPER": ""}
        self.assertEqual(
            paths.default_helper_path("/opt/x/lib/omarchy-clean/src/omarchy_clean/paths.py", env),
            "/opt/x/lib/omarchy-clean/bin/omarchy-clean-helper")

    def test_derived_from_module_path(self):
        self.assertEqual(
            paths.default_helper_path("/opt/x/lib/omarchy-clean/src/omarchy_clean/paths.py", {}),
            "/opt/x/lib/omarchy-clean/bin/omarchy-clean-helper")

    def test_real_module_resolves_to_repo_helper(self):
        result = paths.default_helper_path(environ={})
        self.assertEqual(result, str(ROOT / "bin" / "omarchy-clean-helper"))
        self.assertTrue(Path(result).exists())


class RenderPolicyTest(unittest.TestCase):
    def test_substitutes_and_parses(self):
        helper = "/usr/lib/omarchy-clean/bin/omarchy-clean-helper"
        rendered = paths.render_policy(TEMPLATE, helper)
        self.assertNotIn("@HELPER_PATH@", rendered)
        action = ET.fromstring(rendered).find("action")
        annotate = {a.get("key"): a.text for a in action.findall("annotate")}
        self.assertEqual(annotate[EXEC_PATH], helper)

    def test_missing_placeholder_rejected(self):
        with self.assertRaises(ValueError):
            paths.render_policy("<policyconfig/>", "/abs/helper")

    def test_relative_path_rejected(self):
        with self.assertRaises(ValueError):
            paths.render_policy(TEMPLATE, "bin/helper")


if __name__ == "__main__":
    unittest.main()
