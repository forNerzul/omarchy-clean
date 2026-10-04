"""GTK4 layer-shell overlay that drives the root helper and shows its status."""

from __future__ import annotations

import argparse
from dataclasses import replace
import signal
import subprocess
import sys

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")

from gi.repository import Gdk, Gio, GLib, Gtk, Gtk4LayerShell  # noqa: E402

from omarchy_clean.core import MAX_LOCK_SECONDS  # noqa: E402
from omarchy_clean.paths import default_helper_path  # noqa: E402
from omarchy_clean.picker import pick_duration, resolve_duration  # noqa: E402
from omarchy_clean.overlay_model import (  # noqa: E402
    OverlayState,
    apply_event,
    helper_exit_outcome,
    locked_labels,
    parse_duration_arg,
    parse_status_line,
)

APP_ID = "dev.omarchy.Clean"
UNLOCKED_LINGER_MS = 1000

CSS = b"""
window.omarchy-clean { background-color: #000000; }
.countdown { font-size: 160px; font-weight: bold; color: #ffffff; }
.status { font-size: 32px; color: #dddddd; }
.hint { font-size: 22px; color: #888888; }
.footnote { font-size: 18px; color: #555555; }
progressbar { min-width: 400px; }
"""


def _duration(value: str) -> str:
    try:
        parse_duration_arg(value)
        return value
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="omarchy-clean",
        description="Lock keyboard and trackpad so they can be cleaned.",
    )
    parser.add_argument("duration", nargs="?", type=_duration,
                        default=None,
                        help=f"seconds, 1..{MAX_LOCK_SECONDS}, or 'unlimited' "
                        "(until Esc + Enter); omit to choose from a menu")
    parser.add_argument("--helper",
                        default=default_helper_path(),
                        help="path to the root helper")
    parser.add_argument("--no-pkexec", action="store_true",
                        help="run the helper directly (dev/testing only)")
    return parser.parse_args(argv)


class CleanApp(Gtk.Application):
    def __init__(self, args):
        super().__init__(application_id=APP_ID)
        self.args = args
        self.state = OverlayState(unlimited=args.duration[1])
        self.exit_code = 0
        self.windows = []
        self.widgets = []  # (countdown, progress, status, hint, footnote)
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
        argv = [self.args.helper, str(self.args.duration[0])]
        if not self.args.no_pkexec:
            argv.insert(0, "pkexec")
        try:
            self.subprocess = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_PIPE)
        except GLib.Error as exc:
            self.state = replace(self.state, phase="failed",
                                 message=f"cannot start helper: {exc.message}")
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
        headline, hint_text, footnote_text = locked_labels(self.state)
        countdown = Gtk.Label(label=headline)
        countdown.add_css_class("countdown")
        status = Gtk.Label(label="Keyboard and trackpad locked")
        status.add_css_class("status")
        hint = Gtk.Label(label=hint_text)
        hint.add_css_class("hint")
        progress = Gtk.ProgressBar(halign=Gtk.Align.CENTER)
        progress.set_visible(False)
        footnote = Gtk.Label(label=footnote_text or "")
        footnote.add_css_class("footnote")
        footnote.set_visible(footnote_text is not None)
        for child in (countdown, status, hint, progress, footnote):
            box.append(child)
        window.set_child(box)
        self.widgets.append((countdown, progress, status, hint, footnote))
        return window

    def refresh(self):
        unlocked = self.state.phase == "unlocked"
        headline, _hint, footnote_text = locked_labels(self.state)
        for countdown, progress, status, hint, footnote in self.widgets:
            if unlocked:
                countdown.set_label("Unlocked")
                status.set_label("")
                hint.set_label("")
                footnote.set_visible(False)
                progress.set_visible(False)
                continue
            countdown.set_label(headline)
            if footnote_text is not None:
                footnote.set_label(footnote_text)
            combo = max(0.0, min(1.0, self.state.combo))
            progress.set_fraction(combo)
            progress.set_visible(combo > 0)


def main(argv=None, pick=pick_duration) -> int:
    args = _parse_args(argv)
    duration = resolve_duration(args.duration, pick)
    if duration is None:  # picker cancelled
        return 0
    args.duration = duration
    app = CleanApp(args)
    app.run([sys.argv[0]])
    return app.exit_code
