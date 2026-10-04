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
- Channel: AUR. License MIT; repo github.com/forNerzul/omarchy-clean;
  maintainer Sergio Javier Garcia Martinez. Publishing is a separate user decision.

## Branch

`feat/generic-laptop-support` (from `feat/keyboard-clean-lock`).

## Tasks

- [x] 1. Capability-based device classifier in `core.py` (TDD, pure logic).
- [x] 2. Helper uses the classifier by default; require a keyboard; keep
      `--device` override. Check classification against this machine's sysfs.
- [x] 3. Prefix-independent paths: overlay locates the helper relative to its
      launcher; polkit policy rendered from a template with the helper path.
- [x] 4. `make install` (PREFIX/DESTDIR) for system files incl. desktop entry;
      `omarchy-clean-setup [--remove]` for user steps; `install.sh` and
      `uninstall.sh` become thin wrappers.
- [x] 5. AUR packaging: `packaging/aur/PKGBUILD` + `.SRCINFO`; local build
      check with `makepkg` from the local repo.
- [x] 6. README: supported hardware, AUR/manual install, setup command.

## Evidence

- Task 1: `91ada17` — RED/GREEN, 72 tests; classifier checked against this
  machine's sysfs: 8 devices locked (adds 2 Bluetooth HID devices), lid,
  speaker and 4 jacks excluded, keyboard present.
- Task 2: `4b0e20c` — RED/GREEN, 78 tests.
- Task 3: `c0caf0c` — RED/GREEN, 85 tests.
- Task 4: `0233b1a` — RED/GREEN, `make check` 104 tests; DESTDIR install
  layout inspected (relative symlink, policy exec.path under /usr).
- Task 5: `cb14a88` — RED/GREEN, 107 tests; local `makepkg -f` built
  omarchy-clean-0.1.0-1-any with check() passing; package not installed.
- Task 6: `099638a` — README rewrite (passive docs, `make check` green).
- Review `review-254a4b9b71c2d45c` (914e0cc..099638a): one CRITICAL finding
  (stray `install` copy) corrected in `a964909`, validator approved,
  acknowledged. Stray `uninstall` copy removed separately.

## Follow-ups from review (advisory)

- Lid switch exposed on a device that also has keys (some laptops) gets
  grabbed: lid events and suspend detection could be lost. Exclude EV_SW
  lid/tablet switches or skip such devices.
- Devices hot-plugged during a lock (e.g. Bluetooth keyboard) are not locked.
- One unreadable device aborts the whole lock instead of being skipped.
- `paths.render_policy` is unused (Makefile renders with sed).
- Manual install and AUR package write the same polkit file (documented).

## Pending

- Hardware check of auto-detection with a real lock (reinstall needed:
  `./uninstall.sh && ./install.sh`).
- Release: push, tag v0.1.0, `updpkgsums`, AUR upload (user decisions).
