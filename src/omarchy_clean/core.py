"""Pure, time-injected logic for the keyboard clean-lock helper."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

KEY_ESC = 1
KEY_ENTER = 28
KEY_A = 30
KEY_Z = 44
EV_KEY = 1
EV_REL = 2
EV_ABS = 3
REL_X = 0
REL_Y = 1
ABS_X = 0
ABS_Y = 1
ABS_MT_POSITION_X = 53
ABS_MT_POSITION_Y = 54
BTN_LEFT = 272
BTN_TOOL_FINGER = 325
BTN_TOUCH = 330
DEFAULT_UNLOCK_KEYS: frozenset[int] = frozenset({KEY_ESC, KEY_ENTER})
DEFAULT_HOLD_SECONDS = 3.0
MAX_LOCK_SECONDS = 600
DEFAULT_DEVICE_NAMES: tuple[str, ...] = (
    "Apple Inc. Apple Internal Keyboard / Trackpad",
    "bcm5974",
    "Power Button",
    "Sleep Button",
    "Video Bus",
)


@dataclass(frozen=True)
class DeviceSelection:
    """Matched device paths and wanted names that had no match."""

    paths: tuple[str, ...]
    missing: tuple[str, ...]


def select_devices(
    available: Iterable[tuple[str, str]], wanted: Iterable[str]
) -> DeviceSelection:
    """Select every available device whose name exactly matches a wanted name."""
    wanted_names = tuple(dict.fromkeys(wanted))
    wanted_set = set(wanted_names)
    devices = list(available)
    paths = tuple(dict.fromkeys(p for p, n in devices if n in wanted_set))
    found = {n for _, n in devices}
    missing = tuple(n for n in wanted_names if n not in found)
    return DeviceSelection(paths=paths, missing=missing)


Capabilities = Mapping[int, Sequence[int]]


def classify_device(capabilities: Capabilities) -> str | None:
    """Classify an input device by capabilities; None if it emits no keys/buttons."""
    keys = set(capabilities.get(EV_KEY, ()))
    if not keys:
        return None
    if {KEY_ESC, KEY_ENTER, KEY_A, KEY_Z} <= keys:
        return "keyboard"
    abs_axes = set(capabilities.get(EV_ABS, ()))
    has_axes = {ABS_X, ABS_Y} <= abs_axes or {
        ABS_MT_POSITION_X,
        ABS_MT_POSITION_Y,
    } <= abs_axes
    if has_axes and keys & {BTN_TOUCH, BTN_TOOL_FINGER}:
        return "touch"
    if {REL_X, REL_Y} <= set(capabilities.get(EV_REL, ())):
        return "pointer"
    return "buttons"


@dataclass(frozen=True)
class LockTargets:
    """Devices to lock, with their names and categories in matching order."""

    paths: tuple[str, ...]
    names: tuple[str, ...]
    categories: tuple[str, ...]

    @property
    def has_keyboard(self) -> bool:
        return "keyboard" in self.categories


def select_lock_targets(
    devices: Iterable[tuple[str, str, Capabilities]],
) -> LockTargets:
    """Select every device that can produce key/button events, in input order."""
    seen: set[str] = set()
    paths: list[str] = []
    names: list[str] = []
    categories: list[str] = []
    for path, name, caps in devices:
        category = classify_device(caps)
        if category is None or path in seen:
            continue
        seen.add(path)
        paths.append(path)
        names.append(name)
        categories.append(category)
    return LockTargets(tuple(paths), tuple(names), tuple(categories))


class HoldCombo:
    """Detects a key combination held continuously for a given time."""

    def __init__(
        self,
        keys: frozenset[int] = DEFAULT_UNLOCK_KEYS,
        hold_seconds: float = DEFAULT_HOLD_SECONDS,
    ) -> None:
        if not keys:
            raise ValueError("keys must not be empty")
        if hold_seconds <= 0:
            raise ValueError("hold_seconds must be positive")
        self._keys = frozenset(keys)
        self._hold = hold_seconds
        self._down: set[int] = set()
        self._since: float | None = None

    def update(self, code: int, value: int, now: float) -> None:
        """Feed a key event: value 1=press, 0=release, 2=autorepeat."""
        if code not in self._keys:
            return
        if value == 0:
            self._down.discard(code)
            self._since = None
        elif value == 1:
            self._down.add(code)
            if self._since is None and self._down == self._keys:
                self._since = now

    def progress(self, now: float) -> float:
        """Hold progress in [0.0, 1.0]; 0.0 when not holding."""
        if self._since is None:
            return 0.0
        return min(1.0, max(0.0, (now - self._since) / self._hold))

    def triggered(self, now: float) -> bool:
        """True once the combo has been held for the full duration."""
        return self._since is not None and now - self._since >= self._hold


class LockTimer:
    """Countdown for the lock duration."""

    def __init__(
        self,
        duration: float,
        started_at: float,
        max_duration: float = MAX_LOCK_SECONDS,
    ) -> None:
        if duration <= 0 or duration > max_duration:
            raise ValueError(f"duration must be in (0, {max_duration}]")
        self._duration = duration
        self._started_at = started_at

    def remaining(self, now: float) -> float:
        """Seconds left, never below zero."""
        return max(0.0, self._started_at + self._duration - now)

    def expired(self, now: float) -> bool:
        """True once the duration has elapsed."""
        return self.remaining(now) <= 0.0


class SuspendDetector:
    """Detects a system suspend: boottime advances while monotonic does not."""

    def __init__(self, threshold: float = 2.0) -> None:
        if threshold <= 0:
            raise ValueError("threshold must be positive")
        self._threshold = threshold
        self._last: tuple[float, float] | None = None

    def update(self, monotonic: float, boottime: float) -> bool:
        """Feed a clock sample; True if a suspend happened since the last one."""
        last, self._last = self._last, (monotonic, boottime)
        if last is None:
            return False
        return (boottime - last[1]) - (monotonic - last[0]) > self._threshold
