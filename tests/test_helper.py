import contextlib
import io
import json
import threading
import unittest
from types import SimpleNamespace

from omarchy_clean import helper

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
