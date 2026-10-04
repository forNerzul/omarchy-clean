# Feature: duration-picker

Let the user choose the lock duration when the app opens, including a
"no limit" option, without weakening the safety model.

## Decisions

- Picker: Omarchy's native `omarchy-menu-select` (prints the choice, exit 1
  on cancel). Options: 30 s, 1 min, 2 min, 5 min, No limit. Cancel = exit
  quietly. If the command is missing, fall back to 60 s.
- `omarchy-clean` without arguments opens the picker; `omarchy-clean SECONDS`
  locks directly. The keybind and desktop entry use the picker.
- "No limit" = until Esc + Enter, with a hidden safety cap of 30 minutes
  (the overlay says so in small print). Global hard maximum raised from
  600 s to 1800 s.
- The lid switch must never be grabbed (it is the emergency exit via
  suspend): devices reporting `SW_LID` are skipped even if they have keys.

## Branch

`feat/duration-picker` (from `feat/generic-laptop-support`).

## Tasks

- [ ] 1. Never grab a device that reports the lid switch (TDD).
- [ ] 2. Raise the hard maximum to 1800 s; "no limit" mode in the overlay
      (`omarchy-clean unlimited`): hint-first layout plus small "releases
      automatically in 30 min" note.
- [ ] 3. Duration picker via `omarchy-menu-select` when no argument is given;
      fallback to 60 s when unavailable.
- [ ] 4. Keybind and desktop entry use the picker; `omarchy-clean-setup`
      updates an existing `omarchy-clean 60` block in place.
- [ ] 5. README.

## Evidence

(commit ids and checks recorded per task)
