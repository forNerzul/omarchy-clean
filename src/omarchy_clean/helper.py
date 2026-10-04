"""Root helper: exclusively grabs input devices while the clean-lock runs."""

from __future__ import annotations

import argparse
import json
import os
import select
import signal
import sys
import threading
import time

from omarchy_clean.core import (
    MAX_LOCK_SECONDS,
    HoldCombo,
    LockTimer,
    SuspendDetector,
    classify_device,
    select_devices,
    select_lock_targets,
)

EV_KEY = 1
NO_KEYBOARD_ERROR = "no keyboard found; refusing to lock without a way to unlock"
KEYS_CLEAR_TIMEOUT = 2.0
KEYS_CLEAR_STEP = 0.05


class _OutputClosed(Exception):
    pass


PIPE_BUF = 4096


class NonBlockingLineWriter:
    """Write short lines to a pipe fd without ever blocking.

    Assumes every line is < PIPE_BUF (our JSON status lines are tiny), so a
    pipe write is atomic: it either fully succeeds or raises BlockingIOError.
    Longer lines raise ValueError.
    """

    def __init__(self, fd: int) -> None:
        self.fd = fd
        os.set_blocking(fd, False)

    def write(self, text: str) -> int:
        data = text.encode("utf-8")
        if len(data) >= PIPE_BUF:
            raise ValueError("line too long for an atomic pipe write")
        os.write(self.fd, data)
        return len(text)

    def flush(self) -> None:
        pass


def _emit(out, **obj) -> None:
    """Best-effort status line: drop it if the reader is not keeping up."""
    try:
        out.write(json.dumps(obj) + "\n")
        out.flush()
    except BlockingIOError:  # must precede OSError; the lock must not stall
        pass
    except OSError as exc:  # BrokenPipeError is an OSError
        raise _OutputClosed from exc


def _wait_keys_clear(devices, clock, wait_ready) -> None:
    """Give held keys time to be released; they would autorepeat once grabbed."""
    start = clock()
    while clock() - start < KEYS_CLEAR_TIMEOUT:
        if not any(d.active_keys() for d in devices):
            return
        wait_ready([], KEYS_CLEAR_STEP)


def run_lock(
    devices,
    duration,
    out,
    *,
    clock,
    wait_ready,
    combo=None,
    tick_interval=0.1,
    max_duration=MAX_LOCK_SECONDS,
    stop=None,
    boottime=None,
) -> str:
    """Grab devices, stream JSON status to out, and return the unlock reason."""
    combo = combo if combo is not None else HoldCombo()
    suspend = SuspendDetector() if boottime is not None else None
    stop = stop if stop is not None else threading.Event()
    grabbed = []
    reason = "error"
    try:
        try:
            timer = LockTimer(duration, clock(), max_duration)
            _wait_keys_clear(devices, clock, wait_ready)
            try:
                for dev in devices:
                    dev.grab()
                    grabbed.append(dev)
            except OSError as exc:
                _emit(out, event="error", message=f"grab failed: {exc}")
                return _finish(out, "error")
            timer = LockTimer(duration, clock(), max_duration)
            _emit(out, event="locked", devices=[d.name for d in devices], duration=duration)
            by_fd = {d.fd: d for d in devices}
            while True:
                if stop.is_set():
                    reason = "signal"
                    break
                ready = wait_ready(list(by_fd), tick_interval)
                try:
                    for fd in ready:
                        for ev in by_fd[fd].read():
                            if ev.type == EV_KEY:
                                combo.update(ev.code, ev.value, clock())
                except BlockingIOError:
                    pass
                except OSError as exc:
                    _emit(out, event="error", message=f"device error: {exc}")
                    reason = "error"
                    break
                now = clock()
                if suspend is not None and suspend.update(now, boottime()):
                    reason = "suspend"
                    break
                if combo.triggered(now):
                    reason = "combo"
                    break
                if timer.expired(now):
                    reason = "timer"
                    break
                if stop.is_set():
                    reason = "signal"
                    break
                _emit(
                    out,
                    event="tick",
                    remaining=round(timer.remaining(now), 2),
                    combo=round(combo.progress(now), 2),
                )
            return _finish(out, reason)
        except _OutputClosed:
            return "output-closed"
    finally:
        for dev in grabbed:
            try:
                dev.ungrab()
            except Exception:
                pass


def _finish(out, reason: str) -> str:
    _emit(out, event="unlocked", reason=reason)
    return reason


def _parse_args(argv):
    parser = argparse.ArgumentParser(prog="omarchy-clean-helper")
    parser.add_argument("seconds", type=float)
    parser.add_argument(
        "--device",
        action="append",
        metavar="NAME",
        dest="devices",
        help="lock only the device with this exact name (repeatable); "
        "overrides auto-detection",
    )
    args = parser.parse_args(argv)
    if not 0 < args.seconds <= MAX_LOCK_SECONDS:
        parser.error(f"SECONDS must be > 0 and <= {MAX_LOCK_SECONDS}")
    return args


def choose_targets(devices, requested_names):
    """Pick devices to lock: (paths, names, error). devices: (path, name, caps)."""
    devices = list(devices)
    if requested_names:
        selection = select_devices(((p, n) for p, n, _ in devices), requested_names)
        if selection.missing:
            return [], [], "missing devices: " + ", ".join(selection.missing)
        chosen = set(selection.paths)
        picked = [(p, n, c) for p, n, c in devices if p in chosen]
        if not any(classify_device(c) == "keyboard" for _, _, c in picked):
            return [], [], NO_KEYBOARD_ERROR
        return [p for p, _, _ in picked], [n for _, n, _ in picked], None
    targets = select_lock_targets(devices)
    if not targets.has_keyboard:
        return [], [], NO_KEYBOARD_ERROR
    return list(targets.paths), list(targets.names), None


def main(argv=None) -> int:
    args = _parse_args(argv)
    import evdev  # lazy: only needed on the real CLI path

    out = NonBlockingLineWriter(sys.stdout.fileno())

    opened = {}
    try:
        for path in evdev.list_devices():
            try:
                opened[path] = evdev.InputDevice(path)
            except OSError:  # permission denied or device vanished
                continue
        try:
            listing = [
                (p, d.name, d.capabilities(absinfo=False)) for p, d in opened.items()
            ]
        except OSError as exc:
            listing = []
            error = f"cannot read devices: {exc}"
            paths = []
        else:
            paths, _, error = choose_targets(listing, args.devices)
        if error:
            try:
                _emit(out, event="error", message=error)
                _emit(out, event="unlocked", reason="error")
            except _OutputClosed:
                pass
            return 1

        for path in [p for p in opened if p not in paths]:
            try:
                opened.pop(path).close()
            except Exception:
                pass

        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, lambda *_: stop.set())

        def wait_ready(fds, timeout):
            return select.select(fds, [], [], timeout)[0]

        reason = run_lock(
            [opened[p] for p in paths],
            args.seconds,
            out,
            clock=time.monotonic,
            boottime=lambda: time.clock_gettime(time.CLOCK_BOOTTIME),
            wait_ready=wait_ready,
            stop=stop,
        )
        return 1 if reason == "error" else 0
    finally:
        for dev in opened.values():
            try:
                dev.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
