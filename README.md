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
| Keyboards (internal, USB, Bluetooth) | Lid switch (and any device reporting it) |
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
keybind and leaves the agent enabled. Re-running it updates an older
omarchy-clean keybind in place. Both refuse to edit `bindings.lua` if the
markers are inconsistent.

## Uninstall

```sh
omarchy-clean-setup --remove   # then: yay -R omarchy-clean
./uninstall.sh                 # manual installs
```

Switching from a manual install to the AUR package: run `./uninstall.sh` first,
otherwise pacman reports the polkit policy file as already existing.

## Usage

- `omarchy-clean` opens the Omarchy menu to choose 30 s, 1 min, 2 min, 5 min
  or No limit (falls back to 60 s if `omarchy-menu-select` is unavailable).
- `omarchy-clean SECONDS` (1 to 1800) or `omarchy-clean unlimited` skip the
  menu.
- `SUPER + SHIFT + K` and "Clean Keyboard" in the app menu open the picker.

In **No limit** mode there is no timer at all: the lock lasts until you hold
Esc + Enter for 3 seconds or close the lid. The screen shows no countdown.

## Troubleshooting

If the duration menu cannot open (for example the Omarchy shell is not
responding), omarchy-clean still locks for 1 minute and shows a notification.
Pressing Esc in the menu is a normal cancel and does nothing.

Run `omarchy-clean --diagnose` to see:

- a check of everything omarchy-clean needs, with a fix for each failure
  (the most common one: run `omarchy-restart-shell`);
- the last error, explained in plain language;
- a report ready to paste into a
  [GitHub issue](https://github.com/forNerzul/omarchy-clean/issues).

The last error is stored locally in
`~/.local/state/omarchy-clean/last-error.log` (or `$XDG_STATE_HOME`). It holds
only the time, the error, and the Omarchy and omarchy-clean versions; no
personal data. Nothing is ever sent anywhere automatically: you decide whether
to share the report.

## Safety model

- The grab is done by a root helper started per use via `pkexec`
  (password prompt every time); it is not on `PATH` and lives in a root-owned
  directory.
- Devices are grabbed exclusively (`EVIOCGRAB`); the kernel releases the grabs
  if the helper dies.
- If the overlay dies, the helper unlocks; if the overlay stops reading,
  Esc + Enter, the lid and (in timed mode) the timer still work.
- If any locked device stops responding or is unplugged (e.g. a Bluetooth
  keyboard disconnects), the lock ends.
- Timed locks have a hard maximum of 1800 s. No limit mode has no timer; it
  relies on the exits listed here.
- Closing the lid (any suspend) ends the lock, so the normal lock screen is
  usable on resume. Devices reporting the lid switch are never grabbed, so
  this exit always works.
- Holding the power button for several seconds forces a hardware power-off
  as a last resort (unsaved work is lost).

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
