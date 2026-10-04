"""GTK4 layer-shell overlay that drives the root helper and shows its status."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")

from gi.repository import Gdk, Gio, GLib, Gtk, Gtk4LayerShell  # noqa: E402

from omarchy_clean.overlay_model import (  # noqa: E402
    OverlayState,
    apply_event,
    format_remaining,
    helper_exit_outcome,
    parse_status_line,
)

APP_ID = "dev.omarchy.Clean"
DEFAULT_HELPER = "/usr/local/lib/omarchy-clean/bin/omarchy-clean-helper"
DEFAULT_SECONDS = 60
MAX_SECONDS = 600
UNLOCKED_LINGER_MS = 1000

CSS = b"""
window.omarchy-clean { background-color: #000000; }
.countdown { font-size: 160px; font-weight: bold; color: #ffffff; }
.status { font-size: 32px; color: #dddddd; }
.hint { font-size: 22px; color: #888888; }
progressbar { min-width: 400px; }
"""


def _seconds(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid integer: {value!r}") from None
    if not 1 <= n <= MAX_SECONDS:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_SECONDS}")
    return n


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="omarchy-clean",
        description="Lock keyboard and trackpad so they can be cleaned.",
    )
    parser.add_argument("seconds", nargs="?", type=_seconds, default=DEFAULT_SECONDS,
                        help=f"lock duration, 1..{MAX_SECONDS} (default {DEFAULT_SECONDS})")
    parser.add_argument("--helper",
                        default=os.environ.get("OMARCHY_CLEAN_HELPER", DEFAULT_HELPER),
                        help="path to the root helper")
    parser.add_argument("--no-pkexec", action="store_true",
                        help="run the helper directly (dev/testing only)")
    return parser.parse_args(argv)


class CleanApp(Gtk.Application):
    def __init__(self, args):
        super().__init__(application_id=APP_ID)
        self.args = args
        self.state = OverlayState()
        self.exit_code = 0
        self.windows = []
        self.widgets = []  # (countdown, progress, status) per window
        self.subprocess = None
        self.inhibit_cookie = 0
        self.finishing = False
        self.connect("activate", self.on_activate)
        self.connect("shutdown", self.on_shutdown)

    # -- helper process ------------------------------------------------
    def on_activate(self, _app):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        argv = [self.args.helper, str(self.args.seconds)]
        if not self.args.no_pkexec:
            argv.insert(0, "pkexec")
        try:
            self.subprocess = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_PIPE)
        except GLib.Error as exc:
            self.state = OverlayState(phase="failed", message=f"cannot start helper: {exc.message}")
            self.finish()
            return
        self.hold()  # keep the app alive while no window exists
        self.reader = Gio.DataInputStream.new(self.subprocess.get_stdout_pipe())
        self.reader.read_line_async(GLib.PRIORITY_DEFAULT, None, self.on_line)

    def on_line(self, stream, result):
        try:
            line, _length = stream.read_line_finish_utf8(result)
        except GLib.Error:
            line = None
        if line is None:
            self.subprocess.wait_async(None, self.on_exited)
            return
        event = parse_status_line(line)
        if event is not None:
            self.handle_event(event)
        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, self.on_line)

    def on_exited(self, proc, result):
        try:
            proc.wait_finish(result)
            code = proc.get_exit_status() if proc.get_if_exited() else 128 + proc.get_term_sig()
        except GLib.Error:
            code = -1
        self.state = helper_exit_outcome(self.state, code)
        self.finish()

    # -- state handling ------------------------------------------------
    def handle_event(self, event):
        previous = self.state.phase
        self.state = apply_event(self.state, event)
        if self.state.phase == "locked":
            if previous != "locked":
                self.show_windows()
            self.refresh()
        elif self.state.phase == "unlocked" and previous != "unlocked":
            self.refresh()
            self.finish()

    def finish(self):
        if self.finishing:
            return
        self.finishing = True
        phase = self.state.phase
        if phase == "failed":
            self.exit_code = 1
        if self.state.message and phase in ("failed", "unlocked"):
            self.notify(self.state.message)
        if phase == "unlocked":
            GLib.timeout_add(UNLOCKED_LINGER_MS, self.quit_now)
        else:
            self.quit_now()

    def quit_now(self):
        self.quit()
        return GLib.SOURCE_REMOVE

    def notify(self, message):
        try:
            subprocess.Popen(["notify-send", "-u", "critical", "omarchy-clean", message])
        except OSError:
            pass

    def on_shutdown(self, _app):
        if self.inhibit_cookie:
            self.uninhibit(self.inhibit_cookie)
            self.inhibit_cookie = 0
        if self.subprocess is not None and self.subprocess.get_identifier() is not None:
            try:
                self.subprocess.send_signal(signal.SIGTERM)
            except Exception:
                pass

    # -- windows -------------------------------------------------------
    def show_windows(self):
        monitors = Gdk.Display.get_default().get_monitors()
        for i in range(monitors.get_n_items()):
            self.windows.append(self.build_window(monitors.get_item(i)))
        if self.windows and not self.inhibit_cookie:
            self.inhibit_cookie = self.inhibit(
                self.windows[0],
                Gtk.ApplicationInhibitFlags.IDLE | Gtk.ApplicationInhibitFlags.SUSPEND,
                "Cleaning keyboard",
            )
        for window in self.windows:
            window.present()

    def build_window(self, monitor):
        window = Gtk.ApplicationWindow(application=self)
        window.add_css_class("omarchy-clean")
        Gtk4LayerShell.init_for_window(window)
        Gtk4LayerShell.set_layer(window, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_monitor(window, monitor)
        for edge in (Gtk4LayerShell.Edge.TOP, Gtk4LayerShell.Edge.BOTTOM,
                     Gtk4LayerShell.Edge.LEFT, Gtk4LayerShell.Edge.RIGHT):
            Gtk4LayerShell.set_anchor(window, edge, True)
        Gtk4LayerShell.set_exclusive_zone(window, -1)
        Gtk4LayerShell.set_keyboard_mode(window, Gtk4LayerShell.KeyboardMode.NONE)
        Gtk4LayerShell.set_namespace(window, "omarchy-clean")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24,
                      halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        countdown = Gtk.Label(label=format_remaining(self.state.remaining))
        countdown.add_css_class("countdown")
        status = Gtk.Label(label="Keyboard and trackpad locked")
        status.add_css_class("status")
        hint = Gtk.Label(label="Hold Esc + Enter for 3 seconds to unlock")
        hint.add_css_class("hint")
        progress = Gtk.ProgressBar(halign=Gtk.Align.CENTER)
        progress.set_visible(False)
        for child in (countdown, status, hint, progress):
            box.append(child)
        window.set_child(box)
        self.widgets.append((countdown, progress, status))
        return window

    def refresh(self):
        unlocked = self.state.phase == "unlocked"
        for countdown, progress, status in self.widgets:
            if unlocked:
                countdown.set_label("Unlocked")
                status.set_label("")
                progress.set_visible(False)
                continue
            countdown.set_label(format_remaining(self.state.remaining))
            combo = max(0.0, min(1.0, self.state.combo))
            progress.set_fraction(combo)
            progress.set_visible(combo > 0)


def main(argv=None) -> int:
    args = _parse_args(argv)
    app = CleanApp(args)
    app.run([sys.argv[0]])
    return app.exit_code
