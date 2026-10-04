# Feature: generic-laptop-support

Make omarchy-clean work on any laptop running Omarchy and make it
distributable as an Arch (AUR) package.

## Decisions

- Lock every keyboard and pointing device (internal, USB, Bluetooth),
  touchpads, touchscreens, and power/sleep/brightness buttons. Never the lid
  switch or audio/HDMI jacks. Classification is by evdev capabilities, not by
  device name. At least one keyboard is required (Esc+Enter unlock).
- `--device NAME` stays as an explicit override.
- No hardcoded install prefix: the overlay finds the helper next to its own
  launcher; the polkit policy is generated for the real helper path.
- Package installs system files only (`/usr`); per-user steps (keybind,
  hyprpolkitagent) move to an `omarchy-clean-setup` command.
- Channel: AUR. License and GitHub publication are pending user decisions.

## Branch

`feat/generic-laptop-support` (from `feat/keyboard-clean-lock`).

## Tasks

- [ ] 1. Capability-based device classifier in `core.py` (TDD, pure logic).
- [ ] 2. Helper uses the classifier by default; require a keyboard; keep
      `--device` override. Check classification against this machine's sysfs.
- [ ] 3. Prefix-independent paths: overlay locates the helper relative to its
      launcher; polkit policy rendered from a template with the helper path.
- [ ] 4. `make install` (PREFIX/DESTDIR) for system files incl. desktop entry;
      `omarchy-clean-setup [--remove]` for user steps; `install.sh` and
      `uninstall.sh` become thin wrappers.
- [ ] 5. AUR packaging: `packaging/aur/PKGBUILD` + `.SRCINFO`; local build
      check with `makepkg` from the local repo.
- [ ] 6. README: supported hardware, AUR/manual install, setup command.

## Evidence

(commit ids and checks recorded per task)
