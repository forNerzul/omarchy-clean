# Feature: duration-picker

Let the user choose the lock duration when the app opens, including a
"no limit" option, without weakening the safety model.

## Decisions

- Picker: Omarchy's native `omarchy-menu-select` (prints the choice, exit 1
  on cancel). Options: 30 s, 1 min, 2 min, 5 min, No limit. Cancel = exit
  quietly. If the command is missing, fall back to 60 s.
- `omarchy-clean` without arguments opens the picker; `omarchy-clean SECONDS`
  locks directly. The keybind and desktop entry use the picker.
- "No limit" = until Esc + Enter (or lid close); no timer at all (revised
  after user feedback). Timed modes keep a hard maximum of 1800 s.
- The lid switch must never be grabbed (it is the emergency exit via
  suspend): devices reporting `SW_LID` are skipped even if they have keys.

## Branch

`feat/duration-picker` (from `feat/generic-laptop-support`).

## Tasks

- [x] 1. Never grab a device that reports the lid switch (TDD).
- [x] 2. Raise the hard maximum to 1800 s; "no limit" mode in the overlay
      (`omarchy-clean unlimited`): hint-first layout plus small "releases
      automatically in 30 min" note.
- [x] 3. Duration picker via `omarchy-menu-select` when no argument is given;
      fallback to 60 s when unavailable.
- [x] 4. Keybind and desktop entry use the picker; `omarchy-clean-setup`
      updates an existing `omarchy-clean 60` block in place.
- [x] 5. README.

- [ ] 6. True no-limit mode (user feedback: the visible 30 min countdown felt
      deceptive): helper runs without any deadline when started with
      `unlimited`; overlay shows "No time limit", the Esc + Enter hint and
      "or close the lid", no numbers. Exits: Esc + Enter, lid close
      (suspend), device loss, overlay death, hardware power-off. The 1800 s
      cap stays for timed modes only.
- [ ] 7. README: describe the no-limit exits honestly.

## Evidence

- Task 1: `acf525d` — RED (1 failure) then GREEN, 109 tests.
- Task 2: `c89dac1` + `9c3ff03` — RED/GREEN, 116 tests; CLI rejects 1801/bogus.
- Task 3: `867d1ea` — RED/GREEN, 127 tests; picker never run for real.
- Task 4: `5d400de` — RED/GREEN, 129 tests; keybind migration in place.
- Task 5: README (passive docs).

- Review `review-d313014aa9d97b63` (a9b3a98..1bf6c1c): approved without
  corrections, acknowledged.

## Follow-ups from review (advisory)

- A picker failure (e.g. omarchy-shell not running, non-cancel exit code)
  looks like a silent cancel: the keybind does nothing. Distinguish cancel
  from failure and fall back to 60 s or notify.
- Skipped lid-switch devices are not reported anywhere.

## Pending

- Hardware check: reinstall, picker appears from SUPER+SHIFT+K, No limit
  mode layout, Esc + Enter exit, lid close exit.
