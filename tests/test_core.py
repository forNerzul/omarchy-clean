import unittest

from omarchy_clean.core import (
    DEFAULT_DEVICE_NAMES,
    DEFAULT_HOLD_SECONDS,
    DEFAULT_UNLOCK_KEYS,
    KEY_ENTER,
    KEY_ESC,
    MAX_LOCK_SECONDS,
    KEY_A,
    DeviceSelection,
    HoldCombo,
    LockTargets,
    LockTimer,
    SuspendDetector,
    classify_device,
    select_devices,
    select_lock_targets,
)


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


APPLE_KEYS = [1, *range(2, 59), 96, 97, 100, 102, 103, 105, 106, 107, 108, 125, 126]
FIXTURES: dict[str, dict[int, list[int]]] = {
    "Lid Switch": {5: [0]},
    "Power Button": {1: [116]},
    "Sleep Button": {1: [142]},
    "Video Bus": {1: [224, 225, 227, 241, 242, 243, 244]},
    "HDA Intel PCH Headphone": {5: [2]},
    "PC Speaker": {18: [1, 2]},
    "Apple Inc. Apple Internal Keyboard / Trackpad": {
        0: [0, 1, 4, 17],
        1: APPLE_KEYS,
        4: [4],
        17: [0, 1, 2],
    },
    "bcm5974": {
        1: [272, 325, 330, 333, 334, 335],
        3: [0, 1, 24, 28, 47, 48, 49, 52, 53, 54, 57],
    },
}


class ClassifyDeviceTest(unittest.TestCase):
    def test_macbook_fixtures(self) -> None:
        expected = {
            "Lid Switch": None,
            "HDA Intel PCH Headphone": None,
            "PC Speaker": None,
            "Power Button": "buttons",
            "Sleep Button": "buttons",
            "Video Bus": "buttons",
            "Apple Inc. Apple Internal Keyboard / Trackpad": "keyboard",
            "bcm5974": "touch",
        }
        for name, want in expected.items():
            with self.subTest(name=name):
                self.assertEqual(classify_device(FIXTURES[name]), want)

    def test_other_devices(self) -> None:
        mouse = {1: [272, 273, 274], 2: [0, 1, 8]}
        touchscreen = {1: [330], 3: [0, 1, 47, 53, 54, 57]}
        at_kbd = {1: [1, 28, *range(30, 45)]}
        keypad = {1: [1, 28, *range(2, 12)]}
        self.assertEqual(classify_device(mouse), "pointer")
        self.assertEqual(classify_device(touchscreen), "touch")
        self.assertEqual(classify_device(at_kbd), "keyboard")
        self.assertEqual(classify_device(keypad), "buttons")

    def test_empty_or_missing_key_caps(self) -> None:
        self.assertIsNone(classify_device({1: []}))
        self.assertIsNone(classify_device({}))
        self.assertIsNone(classify_device({2: [0, 1]}))

    def test_touch_needs_button_and_axes(self) -> None:
        self.assertEqual(classify_device({1: [330], 3: [0]}), "buttons")
        self.assertEqual(classify_device({1: [272], 3: [0, 1]}), "buttons")
        self.assertEqual(classify_device({1: [325], 3: [0, 1]}), "touch")
        self.assertEqual(classify_device({1: [330], 3: [53, 54]}), "touch")


class SelectLockTargetsTest(unittest.TestCase):
    ORDER = [
        "Lid Switch",
        "Power Button",
        "Sleep Button",
        "Video Bus",
        "HDA Intel PCH Headphone",
        "PC Speaker",
        "Apple Inc. Apple Internal Keyboard / Trackpad",
        "bcm5974",
    ]

    def devices(self, skip: tuple[str, ...] = ()) -> list[tuple[str, str, dict]]:
        return [
            (f"/dev/input/event{i}", n, FIXTURES[n])
            for i, n in enumerate(self.ORDER)
            if n not in skip
        ]

    def test_macbook_selection(self) -> None:
        t = select_lock_targets(self.devices())
        self.assertIsInstance(t, LockTargets)
        self.assertEqual(
            t.names,
            (
                "Power Button",
                "Sleep Button",
                "Video Bus",
                "Apple Inc. Apple Internal Keyboard / Trackpad",
                "bcm5974",
            ),
        )
        self.assertEqual(
            t.paths,
            tuple(f"/dev/input/event{i}" for i in (1, 2, 3, 6, 7)),
        )
        self.assertEqual(
            t.categories, ("buttons", "buttons", "buttons", "keyboard", "touch")
        )
        self.assertTrue(t.has_keyboard)

    def test_no_keyboard(self) -> None:
        t = select_lock_targets(
            self.devices(skip=("Apple Inc. Apple Internal Keyboard / Trackpad",))
        )
        self.assertFalse(t.has_keyboard)
        self.assertEqual(len(t.paths), 4)

    def test_duplicate_path_skipped(self) -> None:
        devs = self.devices()
        devs.append(("/dev/input/event1", "Power Button", FIXTURES["Power Button"]))
        self.assertEqual(len(select_lock_targets(devs).paths), 5)

    def test_empty(self) -> None:
        t = select_lock_targets([])
        self.assertEqual((t.paths, t.names, t.categories), ((), (), ()))
        self.assertFalse(t.has_keyboard)


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
