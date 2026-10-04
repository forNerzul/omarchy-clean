# omarchy-clean

Lock the keyboard, trackpad, and power/brightness keys of a laptop running
Omarchy (Hyprland, Wayland) for a set time, so it can be wiped clean without
triggering anything.

- The lock ends when the timer runs out, or early by holding **Esc + Enter**
  for 3 seconds.
- A privileged helper grabs the input devices exclusively (`EVIOCGRAB`) and
  runs per use through `pkexec`; the fullscreen overlay runs as your user.

## Development

```sh
make test
```
