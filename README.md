# omarchy-clean

Lock the keyboard, trackpad, and power/brightness keys of a laptop running
Omarchy (Hyprland, Wayland) for a set time, so it can be wiped clean without
triggering anything.

- The lock ends when the timer runs out, or early by holding **Esc + Enter**
  for 3 seconds.
- A privileged helper grabs the input devices exclusively (`EVIOCGRAB`) and
  runs per use through `pkexec`; the fullscreen overlay runs as your user.

## Requirements

Arch + Omarchy (Hyprland), with `python-gobject gtk4 gtk4-layer-shell polkit`
plus:

```sh
sudo pacman -S python-evdev hyprpolkitagent
```

## Install / uninstall

```sh
./install.sh      # system files via sudo, keybind, menu entry, polkit agent
./uninstall.sh
```

Options: `--user-only` (skip sudo/system steps), `--no-keybind`; env `PREFIX`
(default `/usr/local`), `HYPR_CONFIG_DIR`, `APPS_DIR`. The installer never
installs packages; it prints the `pacman` command if any are missing. The
keybind is added to `~/.config/hypr/bindings.lua` between
`-- >>> omarchy-clean >>>` markers. Uninstall leaves `hyprpolkitagent` enabled.

## Usage

- `omarchy-clean [SECONDS]` (default 60, max 600)
- `SUPER + SHIFT + K` (locks for 60 s)
- "Clean Keyboard" in the app menu

## Unlocking

The lock ends when the timer runs out, or early by holding **Esc + Enter** for
3 seconds.

## Safety model

- The grab is done by a root helper started per use via `pkexec`
  (password prompt every time); it is not on `PATH`.
- Devices are grabbed exclusively (`EVIOCGRAB`); the kernel releases the grabs
  if the helper dies.
- If the overlay dies, the helper unlocks.
- Hard maximum of 600 s.
- Power, brightness and sleep keys are grabbed too.

## Development

```sh
make test     # unit tests
make check    # tests + bash -n on the scripts
bin/omarchy-clean --helper bin/omarchy-clean-helper 10
```
