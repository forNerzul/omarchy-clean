# Feature: picker-diagnostics

When the duration picker cannot open, never leave the keybind silently dead:
lock anyway with a safe default, tell the user, record what happened, and
give them a way to understand it and report it upstream.

## Decisions

- Cancel vs failure: `omarchy-menu-select` exits 1 with empty stderr on
  cancel. Anything else is a failure: other exit code, exit 1 with stderr,
  unknown choice text, OSError, or timeout.
- `omarchy-menu-select` waits forever if the shell never answers, so the
  picker gets a preflight `omarchy-shell shell ping` (short IPC timeout) and
  a generous overall timeout.
- On failure: lock 60 s anyway and send a desktop notification:
  "Could not open the duration menu. Locking for 1 minute. Details:
  omarchy-clean --diagnose".
- Failure details go to `$XDG_STATE_HOME/omarchy-clean/last-error.log`
  (default `~/.local/state/...`): timestamp, reason, exit code, stderr,
  shell ping result, Omarchy version, omarchy-clean version. Local only,
  nothing personal, never sent anywhere automatically.
- `omarchy-clean --diagnose`: environment checks with plain-language fixes
  (e.g. shell not responding -> `omarchy-restart-shell`), the last error,
  and a copy-ready report plus the issues URL
  https://github.com/forNerzul/omarchy-clean/issues. Works without GTK.

## Branch

`feat/picker-diagnostics` (from `feat/duration-picker`).

## Tasks

- [x] 1. Picker distinguishes cancel from failure (preflight ping, timeout,
      stderr/exit-code rules); on failure lock 60 s and notify (TDD).
- [x] 2. Record failure details in the state-dir error log (TDD).
- [x] 3. `omarchy-clean --diagnose`: checks, last error, report and issue
      URL, no GTK needed (TDD).
- [x] 4. README: troubleshooting and how to report a problem.

Round 2 (user approved the review follow-ups):

- [x] 5. Privacy: replace the home path and `/home/<name>` with `~` /
      `/home/<user>` in the log and in the report; honest privacy note (TDD).
- [ ] 6. No unrequested lock: when the menu may have been shown (timeout,
      exit 1 with stderr) notify and log but do not lock; lock 60 s only
      when the menu surely never appeared (TDD).
- [ ] 7. `--diagnose`: "Everything looks fine" without a report when all
      checks pass and no error is recorded; show the age of the last error
      (TDD).
- [ ] 8. README: update troubleshooting for tasks 5-7.

## Evidence

- Task 1: `394fe72` — RED (import error, 1) then GREEN, 146 tests (2 skipped).
- Task 2: `680fc8e` — RED (6 failures, 4 errors) then GREEN, 157 tests.
  Shell ping outcome lives in `detail` (no extra field).
- Task 4: README troubleshooting (passive docs).
- Task 3: `d7e229f` — RED (21 failures, 1 error) then GREEN, 179 tests;
  `bin/omarchy-clean --diagnose` exit 0 here; simulated shell-unresponsive
  log shows the restart-shell next step.

- Review `review-421d810b885d16b3` (6aaef83..fa58834, high, 4 lenses):
  approved without corrections, acknowledged.

## Follow-ups from review (advisory)

- Report says "no personal data" but pastes stderr verbatim (may contain
  paths with the username): soften the claim or scrub home paths.
- Menu timeout (120 s) and "cancel with stderr" both force a 60 s lock the
  user did not ask for; prefer notify without locking in those cases.
- `--diagnose` shows the last error forever; show its age or clear it after
  a successful pick.
- Readability nits (private `_shell_responds` import, naming).

## Pending

- Hardware check: SUPER+SHIFT+K still opens the picker (not yet confirmed).
- Done: after `./install.sh`, installed `omarchy-clean --diagnose` shows all
  8 checks ok and no recorded error.
- Follow-up: when the shell is down, notify-send likely shows nothing (the
  shell draws notifications); "To report it" is shown even when all is ok.
