import unittest

from omarchy_clean.core import (
    DEFAULT_DEVICE_NAMES,
    DEFAULT_HOLD_SECONDS,
    DEFAULT_UNLOCK_KEYS,
    KEY_ENTER,
    KEY_ESC,
    MAX_LOCK_SECONDS,
    DeviceSelection,
    HoldCombo,
    LockTimer,
    SuspendDetector,
    select_devices,
)

KEY_A = 30


class SelectDevicesTest(unittest.TestCase):
    def test_constants(self) -> None:
        self.assertEqual(KEY_ESC, 1)
        self.assertEqual(KEY_ENTER, 28)
        self.assertEqual(DEFAULT_UNLOCK_KEYS, frozenset({1, 28}))
        self.assertEqual(DEFAULT_HOLD_SECONDS, 3.0)
        self.assertEqual(MAX_LOCK_SECONDS, 600)
        self.assertIn("bcm5974", DEFAULT_DEVICE_NAMES)

    def test_duplicates_order_and_missing(self) -> None:
        available = [
            ("/dev/input/event3", "Power Button"),
            ("/dev/input/event1", "bcm5974"),
            ("/dev/input/event0", "Power Button"),
            ("/dev/input/event9", "Other"),
        ]
        sel = select_devices(available, ["bcm5974", "Power Button", "Video Bus", "Sleep Button"])
        self.assertIsInstance(sel, DeviceSelection)
        self.assertEqual(
            sel.paths,
            ("/dev/input/event3", "/dev/input/event1", "/dev/input/event0"),
        )
        self.assertEqual(sel.missing, ("Video Bus", "Sleep Button"))

    def test_exact_match_only(self) -> None:
        sel = select_devices([("/p", "Power Button 2")], ["Power Button"])
        self.assertEqual(sel.paths, ())
        self.assertEqual(sel.missing, ("Power Button",))

    def test_no_duplicate_paths_with_repeated_wanted(self) -> None:
        sel = select_devices([("/p", "bcm5974")], ["bcm5974", "bcm5974"])
        self.assertEqual(sel.paths, ("/p",))


class HoldComboTest(unittest.TestCase):
    def test_triggers_at_exactly_hold_seconds(self) -> None:
        c = HoldCombo()
        c.update(KEY_ESC, 1, 10.0)
        self.assertEqual(c.progress(10.5), 0.0)
        c.update(KEY_ENTER, 1, 11.0)
        self.assertEqual(c.progress(11.0), 0.0)
        self.assertAlmostEqual(c.progress(12.5), 0.5)
        self.assertFalse(c.triggered(13.9))
        self.assertTrue(c.triggered(14.0))
        self.assertEqual(c.progress(20.0), 1.0)

    def test_release_cancels_and_repress_restarts(self) -> None:
        c = HoldCombo()
        c.update(KEY_ESC, 1, 0.0)
        c.update(KEY_ENTER, 1, 0.0)
        c.update(KEY_ENTER, 0, 2.0)
        self.assertEqual(c.progress(2.5), 0.0)
        self.assertFalse(c.triggered(10.0))
        c.update(KEY_ENTER, 1, 5.0)
        self.assertFalse(c.triggered(7.9))
        self.assertTrue(c.triggered(8.0))

    def test_autorepeat_does_not_reset(self) -> None:
        c = HoldCombo()
        c.update(KEY_ESC, 1, 0.0)
        c.update(KEY_ENTER, 1, 0.0)
        c.update(KEY_ENTER, 2, 1.0)
        c.update(KEY_ESC, 2, 2.0)
        self.assertTrue(c.triggered(3.0))

    def test_unrelated_key_does_not_cancel(self) -> None:
        c = HoldCombo()
        c.update(KEY_ESC, 1, 0.0)
        c.update(KEY_ENTER, 1, 0.0)
        c.update(KEY_A, 1, 1.0)
        c.update(KEY_A, 0, 2.0)
        self.assertTrue(c.triggered(3.0))

    def test_single_key_never_triggers(self) -> None:
        c = HoldCombo()
        c.update(KEY_ESC, 1, 0.0)
        c.update(KEY_ESC, 2, 5.0)
        self.assertFalse(c.triggered(100.0))
        self.assertEqual(c.progress(100.0), 0.0)

    def test_validation(self) -> None:
        with self.assertRaises(ValueError):
            HoldCombo(keys=frozenset())
        with self.assertRaises(ValueError):
            HoldCombo(hold_seconds=0)
        with self.assertRaises(ValueError):
            HoldCombo(hold_seconds=-1)


class LockTimerTest(unittest.TestCase):
    def test_remaining_clamp_expired(self) -> None:
        t = LockTimer(30, started_at=100.0)
        self.assertEqual(t.remaining(100.0), 30)
        self.assertEqual(t.remaining(110.0), 20)
        self.assertFalse(t.expired(129.9))
        self.assertTrue(t.expired(130.0))
        self.assertEqual(t.remaining(500.0), 0.0)

    def test_validation(self) -> None:
        with self.assertRaises(ValueError):
            LockTimer(0, 0.0)
        with self.assertRaises(ValueError):
            LockTimer(-5, 0.0)
        with self.assertRaises(ValueError):
            LockTimer(MAX_LOCK_SECONDS + 1, 0.0)
        LockTimer(MAX_LOCK_SECONDS, 0.0)
        with self.assertRaises(ValueError):
            LockTimer(20, 0.0, max_duration=10)


if __name__ == "__main__":
    unittest.main()


class SuspendDetectorTest(unittest.TestCase):
    def test_first_sample_false(self) -> None:
        self.assertFalse(SuspendDetector().update(10.0, 500.0))

    def test_normal_ticks_false(self) -> None:
        d = SuspendDetector()
        for i in range(5):
            self.assertFalse(d.update(10.0 + i, 500.0 + i))

    def test_boottime_jump_true(self) -> None:
        d = SuspendDetector()
        d.update(10.0, 500.0)
        self.assertTrue(d.update(10.1, 530.0))
        self.assertFalse(d.update(10.2, 530.1))

    def test_small_drift_false(self) -> None:
        d = SuspendDetector()
        d.update(10.0, 500.0)
        self.assertFalse(d.update(11.0, 512.0 - 9.5))

    def test_threshold_validation(self) -> None:
        for bad in (0, -1.0):
            with self.assertRaises(ValueError):
                SuspendDetector(bad)
