# Feature: keyboard-clean-lock

Lock the MacBookPro12,1 keyboard + trackpad (and power/brightness keys) for a
set time so the laptop can be wiped clean on Omarchy (Hyprland 0.56, Wayland).

## Decisions

- Unlock: timer ends the lock, or hold Esc+Enter for 3 s to end it early.
- UI: unprivileged GTK4 layer-shell fullscreen overlay (dark, countdown).
- Privilege: root helper launched per use with `pkexec`; GUI never runs as root.
- Stack: Python 3 + python-evdev; tests with stdlib `unittest`.
- Mechanism: `EVIOCGRAB` on devices matched by name; kernel releases grabs
  when the helper exits. Helper enforces a hard maximum duration.
- Polkit agent: `hyprpolkitagent` as a systemd user service (uwsm session),
  enabled by `install.sh` instead of `autostart.lua`.
- Keybind: `SUPER + SHIFT + K` in `~/.config/hypr/bindings.lua` (marker block).

## Branch

`feat/keyboard-clean-lock`

## Tasks

- [x] 1. Scaffold project (layout, `.gitignore`, test runner, README stub).
- [x] 2. Helper core logic (TDD): device selection by name, hold-combo
      detector, lock timer/deadline with hard max; no evdev import.
- [x] 3. Helper runtime: evdev grab loop, JSON-lines status protocol on
      stdout, signal handling, CLI (`omarchy-clean-helper <seconds>`).
- [x] 4. Overlay + launcher: GTK4 layer-shell window, spawns helper via
      `pkexec`, renders countdown and combo progress, exits on helper end.
- [x] 5. Install + docs: install script (`/usr/local`), polkit action,
      Hyprland keybind, hyprpolkitagent autostart, README usage and safety.

## Evidence

- Task 1: `336cdf5` — `make test` runner works (0 tests, exit 5 expected).
- Task 2: `6f791bd` — RED (ModuleNotFoundError) then GREEN, 12 unittest tests OK.
- Task 3: `037a262` — RED (ImportError) then GREEN, 25 tests OK; real evdev
  path not exercised (python-evdev not installed).
- Task 4: `4a3ceef` — RED then GREEN, 38 tests OK; overlay import/--help/arg
  checks only, never launched for real.
- Task 5: `8670980` — RED then GREEN, `make check` 46 tests OK (1 skip:
  root-refusal test), `bash -n` clean; installer only tested `--user-only`
  with stubs.

## Manual verification still pending (needs sudo + packages)

- Real lock on hardware: devices grabbed, keys/trackpad/power key blocked,
  timer unlock, Esc+Enter hold unlock, overlay on screen, idle not locking.
- System install steps of `install.sh`.

## Pending user actions

- `sudo pacman -S python-evdev hyprpolkitagent` (sudo needs a password).
