import unittest

from omarchy_clean.overlay_model import (
    OverlayState,
    apply_event,
    format_remaining,
    helper_exit_outcome,
    locked_labels,
    parse_duration_arg,
    parse_status_line,
)


class ParseStatusLineTests(unittest.TestCase):
    def test_valid_object(self):
        self.assertEqual(
            parse_status_line('{"event":"tick","remaining":1.5}\n'),
            {"event": "tick", "remaining": 1.5},
        )

    def test_ignored_lines(self):
        for line in ["", "  \n", "nope", "[1]", "3", '{"a":1}', '{"event":5}']:
            self.assertIsNone(parse_status_line(line), line)


class FormatRemainingTests(unittest.TestCase):
    def test_values(self):
        self.assertEqual(format_remaining(0.2), "0:01")
        self.assertEqual(format_remaining(60), "1:00")
        self.assertEqual(format_remaining(0), "0:00")
        self.assertEqual(format_remaining(-3), "0:00")
        self.assertEqual(format_remaining(59.01), "1:00")
        self.assertEqual(format_remaining(125), "2:05")


class ApplyEventTests(unittest.TestCase):
    def test_locked_then_tick(self):
        s = apply_event(OverlayState(), {"event": "locked", "duration": 30})
        self.assertEqual((s.phase, s.remaining), ("locked", 30))
        s = apply_event(s, {"event": "tick", "remaining": 12.5, "combo": 0.4})
        self.assertEqual((s.remaining, s.combo), (12.5, 0.4))

    def test_tick_ignored_unless_locked(self):
        s = OverlayState()
        self.assertEqual(apply_event(s, {"event": "tick", "remaining": 5, "combo": 1}), s)

    def test_error_keeps_phase(self):
        s = apply_event(OverlayState(phase="locked"), {"event": "error", "message": "boom"})
        self.assertEqual((s.phase, s.message), ("locked", "boom"))

    def test_unlocked(self):
        s = apply_event(OverlayState(phase="locked"), {"event": "unlocked", "reason": "combo"})
        self.assertEqual((s.phase, s.reason), ("unlocked", "combo"))

    def test_unlocked_suspend(self):
        s = apply_event(OverlayState(phase="locked"), {"event": "unlocked", "reason": "suspend"})
        self.assertEqual((s.phase, s.reason), ("unlocked", "suspend"))

    def test_unknown_unchanged(self):
        s = OverlayState()
        self.assertEqual(apply_event(s, {"event": "zzz"}), s)


class HelperExitTests(unittest.TestCase):
    def test_unlocked_unchanged(self):
        s = OverlayState(phase="unlocked", reason="timer")
        self.assertEqual(helper_exit_outcome(s, 1), s)

    def test_auth_dismissed(self):
        for code in (126, 127):
            self.assertEqual(helper_exit_outcome(OverlayState(), code).phase, "cancelled")

    def test_126_after_locked_is_failed(self):
        s = helper_exit_outcome(OverlayState(phase="locked"), 126)
        self.assertEqual(s.phase, "failed")
        self.assertEqual(s.message, "helper exited with code 126")

    def test_failed_keeps_message(self):
        s = helper_exit_outcome(OverlayState(message="no devices"), 1)
        self.assertEqual((s.phase, s.message), ("failed", "no devices"))

    def test_failed_default_message(self):
        s = helper_exit_outcome(OverlayState(), 3)
        self.assertEqual(s.message, "helper exited with code 3")


class ParseDurationArgTests(unittest.TestCase):
    def test_unlimited(self):
        self.assertEqual(parse_duration_arg("unlimited"), (1800, True))
        self.assertEqual(parse_duration_arg("UNLIMITED"), (1800, True))

    def test_integers(self):
        self.assertEqual(parse_duration_arg("60"), (60, False))
        self.assertEqual(parse_duration_arg("1800"), (1800, False))

    def test_invalid(self):
        for text in ["0", "1801", "-5", "abc", ""]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_duration_arg(text)


class LockedLabelsTests(unittest.TestCase):
    def test_timed(self):
        s = OverlayState(phase="locked", remaining=65)
        self.assertEqual(
            locked_labels(s),
            ("1:05", "Hold Esc + Enter for 3 seconds to unlock", None),
        )

    def test_unlimited(self):
        s = OverlayState(phase="locked", remaining=65, unlimited=True)
        self.assertEqual(
            locked_labels(s),
            (
                "No time limit",
                "Hold Esc + Enter for 3 seconds to unlock",
                "Releases automatically in 1:05",
            ),
        )

    def test_unlimited_survives_events(self):
        s = OverlayState(unlimited=True)
        s = apply_event(s, {"event": "locked", "duration": 1800})
        s = apply_event(s, {"event": "tick", "remaining": 5, "combo": 0})
        self.assertTrue(s.unlimited)
        self.assertTrue(helper_exit_outcome(s, 1).unlimited)


if __name__ == "__main__":
    unittest.main()
