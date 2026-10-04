import contextlib
import io
import json
import os
import threading
import unittest
from types import SimpleNamespace

from omarchy_clean import helper
from tests.test_core import FIXTURES

EV_KEY = 1
ESC, ENTER = 1, 28


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class FakeDevice:
    def __init__(self, clock, fd, name="kbd", grab_error=None, read_error=None):
        self.clock = clock
        self.fd = fd
        self.name = name
        self.path = f"/dev/input/event{fd}"
        self.events = []
        self.grabbed = False
        self.ungrab_calls = 0
        self.grab_error = grab_error
        self.read_error = read_error
        self.keys_until = None  # active_keys non-empty until this clock time

    def grab(self):
        if self.grab_error:
            raise self.grab_error
        self.grabbed = True

    def ungrab(self):
        self.ungrab_calls += 1
        self.grabbed = False

    def active_keys(self):
        if self.keys_until is not None and self.clock.t < self.keys_until:
            return [30]
        return []

    def read(self):
        if self.read_error:
            raise self.read_error
        if not self.events:
            raise BlockingIOError
        evs, self.events = self.events, []
        return iter(evs)


def key(code, value):
    return SimpleNamespace(type=EV_KEY, code=code, value=value)


class BrokenOut:
    def write(self, s):
        raise BrokenPipeError

    def flush(self):
        pass


class Env:
    def __init__(self, n=2):
        self.clock = FakeClock()
        self.devices = [FakeDevice(self.clock, i + 10, f"d{i}") for i in range(n)]
        self.out = io.StringIO()
        self.on_wait = None

    def wait_ready(self, fds, timeout):
        self.clock.t += timeout
        if self.on_wait:
            self.on_wait()
        return [d.fd for d in self.devices if d.fd in fds and d.events]

    def run(self, duration=1.0, **kw):
        return helper.run_lock(
            self.devices, duration, kw.pop("out", self.out),
            clock=self.clock, wait_ready=self.wait_ready, **kw,
        )

    def lines(self):
        return [json.loads(x) for x in self.out.getvalue().splitlines()]


class RunLockTests(unittest.TestCase):
    def test_timer_grabs_then_ungrabs_all(self):
        env = Env()
        seen = []
        env.on_wait = lambda: seen.append(all(d.grabbed for d in env.devices))
        self.assertEqual(env.run(1.0), "timer")
        self.assertTrue(all(seen) and seen)
        for d in env.devices:
            self.assertFalse(d.grabbed)
            self.assertEqual(d.ungrab_calls, 1)

    def test_json_sequence(self):
        env = Env()
        env.run(1.0)
        lines = env.lines()
        self.assertEqual(lines[0], {"event": "locked", "devices": ["d0", "d1"], "duration": 1.0})
        ticks = [l for l in lines[1:-1]]
        self.assertTrue(ticks)
        for t in ticks:
            self.assertEqual(set(t), {"event", "remaining", "combo"})
            self.assertEqual(t["event"], "tick")
        self.assertEqual(lines[-1], {"event": "unlocked", "reason": "timer"})
        self.assertTrue(env.out.getvalue().endswith("\n"))

    def test_combo_ends_early(self):
        env = Env()
        env.devices[0].events = [key(ESC, 1), key(ENTER, 1)]
        self.assertEqual(env.run(60.0), "combo")
        self.assertLess(env.clock.t, 100.0 + 10)
        self.assertEqual(env.lines()[-1], {"event": "unlocked", "reason": "combo"})
        self.assertTrue(all(d.ungrab_calls == 1 for d in env.devices))

    def test_suspend_ends_lock(self):
        env = Env()
        offset = [0.0]
        calls = [0]

        def jump():
            calls[0] += 1
            if calls[0] == 5:
                offset[0] += 60.0

        env.on_wait = jump
        self.assertEqual(
            env.run(300.0, boottime=lambda: env.clock.t + offset[0]), "suspend"
        )
        self.assertLess(env.clock.t, 100.0 + 10)
        self.assertTrue(all(d.ungrab_calls == 1 and not d.grabbed for d in env.devices))
        self.assertEqual(env.lines()[-1], {"event": "unlocked", "reason": "suspend"})

    def test_boottime_without_jump_times_out(self):
        env = Env()
        self.assertEqual(env.run(1.0, boottime=lambda: env.clock.t + 5.0), "timer")

    def test_waits_for_active_keys_to_clear(self):
        env = Env()
        env.devices[0].keys_until = 100.3
        grab_time = []
        orig = env.devices[0].grab
        env.devices[0].grab = lambda: (grab_time.append(env.clock.t), orig())
        self.assertEqual(env.run(1.0), "timer")
        self.assertGreaterEqual(grab_time[0], 100.3)
        self.assertLess(grab_time[0], 100.5)

    def test_gives_up_after_two_seconds_and_still_grabs(self):
        env = Env()
        env.devices[0].keys_until = 1e9
        grab_time = []
        orig = env.devices[0].grab
        env.devices[0].grab = lambda: (grab_time.append(env.clock.t), orig())
        self.assertEqual(env.run(1.0), "timer")
        self.assertAlmostEqual(grab_time[0] - 100.0, 2.0, delta=0.1)

    def test_grab_failure_ungrabs_earlier(self):
        env = Env(3)
        env.devices[2].grab_error = OSError(16, "busy")
        self.assertEqual(env.run(1.0), "error")
        self.assertEqual(env.devices[0].ungrab_calls, 1)
        self.assertEqual(env.devices[1].ungrab_calls, 1)
        self.assertFalse(any(d.grabbed for d in env.devices))
        lines = env.lines()
        self.assertEqual(lines[-2]["event"], "error")
        self.assertEqual(lines[-1], {"event": "unlocked", "reason": "error"})
        self.assertNotIn("locked", [l["event"] for l in lines])

    def test_device_read_oserror(self):
        env = Env()
        env.devices[1].events = [key(30, 1)]
        env.devices[1].read_error = OSError(19, "No such device")
        self.assertEqual(env.run(5.0), "error")
        self.assertTrue(all(d.ungrab_calls == 1 for d in env.devices))
        lines = env.lines()
        self.assertEqual(lines[-2]["event"], "error")
        self.assertEqual(lines[-1]["reason"], "error")

    def test_stop_flag(self):
        env = Env()
        stop = threading.Event()
        env.on_wait = stop.set
        self.assertEqual(env.run(30.0, stop=stop), "signal")
        self.assertEqual(env.lines()[-1], {"event": "unlocked", "reason": "signal"})
        self.assertTrue(all(d.ungrab_calls == 1 for d in env.devices))

    def test_output_closed(self):
        env = Env()
        self.assertEqual(env.run(5.0, out=BrokenOut()), "output-closed")
        self.assertTrue(all(d.ungrab_calls == 1 for d in env.devices))

    def test_output_closed_midway(self):
        env = Env()

        class Dying(io.StringIO):
            def write(self, s):
                if self.getvalue().count("\n") >= 2:
                    raise BrokenPipeError
                return super().write(s)

        out = Dying()
        self.assertEqual(env.run(5.0, out=out), "output-closed")
        self.assertEqual(out.getvalue().count("\n"), 2)
        self.assertTrue(all(d.ungrab_calls == 1 for d in env.devices))


class BlockedOut:
    """Writer whose write raises BlockingIOError for the first `blocked` calls (None = always)."""

    def __init__(self, blocked=None, block_if=None):
        self.blocked = blocked
        self.block_if = block_if
        self.calls = 0
        self.written = []

    def write(self, s):
        self.calls += 1
        if self.block_if is not None:
            if self.block_if(self.calls, s):
                raise BlockingIOError
        elif self.blocked is None or self.calls <= self.blocked:
            raise BlockingIOError
        self.written.append(json.loads(s))
        return len(s)

    def flush(self):
        pass


class BlockingWriterTests(unittest.TestCase):
    def test_timer_ends_while_writes_block(self):
        env = Env()
        out = BlockedOut()
        self.assertEqual(env.run(1.0, out=out), "timer")
        self.assertGreater(out.calls, 1)
        self.assertTrue(all(d.ungrab_calls == 1 and not d.grabbed for d in env.devices))

    def test_combo_ends_while_writes_block(self):
        env = Env()
        env.devices[0].events = [key(ESC, 1), key(ENTER, 1)]
        self.assertEqual(env.run(60.0, out=BlockedOut()), "combo")
        self.assertTrue(all(d.ungrab_calls == 1 for d in env.devices))

    def test_later_lines_arrive_after_temporary_blocking(self):
        env = Env()
        # Block only tick lines, and only the first few of them.
        out = BlockedOut(block_if=lambda n, s: '"tick"' in s and n <= 4)
        self.assertEqual(env.run(1.0, out=out), "timer")
        events = [l["event"] for l in out.written]
        self.assertEqual(events[0], "locked")
        self.assertEqual(events[-1], "unlocked")
        self.assertIn("tick", events)

    def test_blocked_unlocked_line_is_dropped(self):
        env = Env()
        out = BlockedOut(block_if=lambda n, s: '"unlocked"' in s)
        self.assertEqual(env.run(1.0, out=out), "timer")
        self.assertNotIn("unlocked", [l["event"] for l in out.written])
        self.assertTrue(all(d.ungrab_calls == 1 for d in env.devices))

    def test_blocked_error_line_is_dropped(self):
        env = Env(3)
        env.devices[2].grab_error = OSError(16, "busy")
        self.assertEqual(env.run(1.0, out=BlockedOut()), "error")
        self.assertEqual([d.ungrab_calls for d in env.devices], [1, 1, 0])


class NonBlockingLineWriterTests(unittest.TestCase):
    def setUp(self):
        self.r, self.w = os.pipe()
        self.addCleanup(os.close, self.r)
        self.addCleanup(os.close, self.w)

    def test_round_trip(self):
        writer = helper.NonBlockingLineWriter(self.w)
        writer.write('{"event": "tick"}\n')
        writer.flush()
        self.assertEqual(os.read(self.r, 100), b'{"event": "tick"}\n')

    def test_full_pipe_raises_instead_of_hanging(self):
        writer = helper.NonBlockingLineWriter(self.w)
        line = "x" * 99 + "\n"
        with self.assertRaises(BlockingIOError):
            for _ in range(100000):
                writer.write(line)
        self.assertFalse(os.get_blocking(self.w))

    def test_oversized_line_rejected(self):
        writer = helper.NonBlockingLineWriter(self.w)
        with self.assertRaises(ValueError):
            writer.write("x" * 5000)


class ChooseTargetsTests(unittest.TestCase):
    NAMES = [
        "Lid Switch",
        "Power Button",
        "Apple Inc. Apple Internal Keyboard / Trackpad",
        "bcm5974",
    ]

    def _devices(self, names=None):
        names = self.NAMES if names is None else names
        return [(f"/dev/input/event{i}", n, FIXTURES[n]) for i, n in enumerate(names)]

    def test_auto_selects_inputs_and_skips_switch_only(self):
        paths, names, error = helper.choose_targets(self._devices(), None)
        self.assertIsNone(error)
        self.assertEqual(paths, ["/dev/input/event1", "/dev/input/event2", "/dev/input/event3"])
        self.assertEqual(names, self.NAMES[1:])

    def test_auto_without_keyboard_errors(self):
        devices = self._devices(["Lid Switch", "Power Button", "bcm5974"])
        paths, names, error = helper.choose_targets(devices, [])
        self.assertEqual((paths, names), ([], []))
        self.assertIn("no keyboard found", error)

    def test_auto_with_nothing_errors(self):
        paths, _, error = helper.choose_targets(self._devices(["Lid Switch"]), None)
        self.assertEqual(paths, [])
        self.assertIsNotNone(error)

    def test_override_selects_named_devices(self):
        wanted = ["bcm5974", "Apple Inc. Apple Internal Keyboard / Trackpad"]
        paths, names, error = helper.choose_targets(self._devices(), wanted)
        self.assertIsNone(error)
        self.assertEqual(paths, ["/dev/input/event2", "/dev/input/event3"])
        self.assertEqual(sorted(names), sorted(wanted))

    def test_override_missing_name_errors(self):
        wanted = ["Apple Inc. Apple Internal Keyboard / Trackpad", "Nope"]
        paths, _, error = helper.choose_targets(self._devices(), wanted)
        self.assertEqual(paths, [])
        self.assertIn("Nope", error)

    def test_override_without_keyboard_errors(self):
        paths, _, error = helper.choose_targets(self._devices(), ["bcm5974"])
        self.assertEqual(paths, [])
        self.assertIn("no keyboard found", error)


class MainTests(unittest.TestCase):
    def _main(self, argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                return helper.main(argv), err.getvalue()
            except SystemExit as e:
                return e.code, err.getvalue()

    def test_rejects_zero(self):
        code, err = self._main(["0"])
        self.assertEqual(code, 2)
        self.assertTrue(err)

    def test_rejects_too_long(self):
        code, _ = self._main(["601"])
        self.assertEqual(code, 2)

    def test_rejects_negative(self):
        code, _ = self._main(["-5"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
