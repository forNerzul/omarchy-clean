"""Install-location helpers: locate the helper and render the polkit policy."""

from __future__ import annotations

import os

PLACEHOLDER = "@HELPER_PATH@"


def default_helper_path(module_file: str | None = None, environ=os.environ) -> str:
    override = environ.get("OMARCHY_CLEAN_HELPER")
    if override:
        return override
    package_dir = os.path.dirname(os.path.realpath(module_file or __file__))
    root = os.path.dirname(os.path.dirname(package_dir))
    return os.path.join(root, "bin", "omarchy-clean-helper")


def render_policy(template: str, helper_path: str) -> str:
    if PLACEHOLDER not in template:
        raise ValueError(f"policy template has no {PLACEHOLDER} placeholder")
    if not os.path.isabs(helper_path):
        raise ValueError(f"helper path must be absolute: {helper_path!r}")
    return template.replace(PLACEHOLDER, helper_path)
