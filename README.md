# omarchy-clean

Lock every keyboard, touchpad, mouse, touchscreen, and power/brightness key of
a laptop running Omarchy (Hyprland, Wayland) for a set time, so it can be wiped
clean without triggering anything.

- The lock ends when the timer runs out, or early by holding **Esc + Enter**
  for 3 seconds.
- A privileged helper grabs the input devices exclusively (`EVIOCGRAB`) and
  runs per use through `pkexec`; the fullscreen overlay runs as your user.

## What gets locked

Devices are detected by what they can do, not by name, so it works on any
laptop:

| Locked | Not touched |
|---|---|
| Keyboards (internal, USB, Bluetooth) | Lid switch |
| Touchpads, touchscreens, mice | Audio and HDMI jacks |
| Power, sleep, brightness and hotkey buttons | PC speaker |

At least one keyboard is required, because it is the only way to unlock early.
To lock specific devices instead, run the helper with `--device NAME`
(repeatable).

## Install

### From the AUR

```sh
yay -S omarchy-clean
omarchy-clean-setup        # as your user: SUPER+SHIFT+K and polkit agent
```

### Manually

```sh
sudo pacman -S python-evdev python-gobject gtk4 gtk4-layer-shell polkit hyprpolkitagent
./install.sh               # make install via sudo (PREFIX=/usr/local) + omarchy-clean-setup
```

Options: `--user-only` (only the per-user setup), `--no-keybind`; env `PREFIX`.
`install.sh` never installs packages; it prints the `pacman` command if any are
missing.

### Per-user setup

`omarchy-clean-setup` enables `hyprpolkitagent.service` (needed for the
password prompt when launched from a keybind or the menu) and adds
`SUPER + SHIFT + K` to `~/.config/hypr/bindings.lua` between
`-- >>> omarchy-clean >>>` markers. `omarchy-clean-setup --remove` removes the
keybind and leaves the agent enabled. Both refuse to edit `bindings.lua` if the
markers are inconsistent.

## Uninstall

```sh
omarchy-clean-setup --remove   # then: yay -R omarchy-clean
./uninstall.sh                 # manual installs
```

Switching from a manual install to the AUR package: run `./uninstall.sh` first,
otherwise pacman reports the polkit policy file as already existing.

## Usage

- `omarchy-clean [SECONDS]` (default 60, max 600)
- `SUPER + SHIFT + K` (locks for 60 s)
- "Clean Keyboard" in the app menu

## Safety model

- The grab is done by a root helper started per use via `pkexec`
  (password prompt every time); it is not on `PATH` and lives in a root-owned
  directory.
- Devices are grabbed exclusively (`EVIOCGRAB`); the kernel releases the grabs
  if the helper dies.
- If the overlay dies, the helper unlocks; if the overlay stops reading, the
  timer and Esc + Enter still work.
- Hard maximum of 600 s.
- Closing the lid (any suspend) ends the lock, so the normal lock screen is
  usable on resume.

## Development

```sh
make test     # unit tests
make check    # tests + bash -n on the scripts
bin/omarchy-clean --helper bin/omarchy-clean-helper 10
make DESTDIR=/tmp/stage PREFIX=/usr install   # inspect the package layout
```

Packaging lives in `packaging/aur/`. After changing `PKGBUILD`, regenerate
`.SRCINFO` with `makepkg --printsrcinfo > .SRCINFO`.

## License

MIT — see `LICENSE`.
