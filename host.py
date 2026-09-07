#!/usr/bin/env python3
import asyncio
import hmac
import html
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

# GI is imported only for a real desktop session, never for --demo or tests.
Gio = GLib = BUS = None
WIDTH, HEIGHT, FPS, BITRATE, AUDIO_BITRATE = 1920, 1080, 60, 6000, 128000
STREAM_NAME = "monitor"
REQUESTED_AUDIO = "auto"
LOG_DIR = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "gnome-web-display"


def initialize(cfg):
    global Gio, GLib, BUS, WIDTH, HEIGHT, FPS, BITRATE, AUDIO_BITRATE, STREAM_NAME, REQUESTED_AUDIO
    import gi
    gi.require_version("Gio", "2.0")
    gi.require_version("GLib", "2.0")
    from gi.repository import Gio as _Gio, GLib as _GLib
    Gio, GLib = _Gio, _GLib
    BUS = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    WIDTH, HEIGHT, FPS, BITRATE = cfg.width, cfg.height, cfg.fps, cfg.bitrate
    AUDIO_BITRATE, STREAM_NAME, REQUESTED_AUDIO = cfg.audio_bitrate, cfg.stream_name, cfg.audio_source


RD_BUS = "org.gnome.Mutter.RemoteDesktop"
RD_ROOT = "/org/gnome/Mutter/RemoteDesktop"
RD_IFACE = "org.gnome.Mutter.RemoteDesktop"
RD_SESSION_IFACE = "org.gnome.Mutter.RemoteDesktop.Session"

SC_BUS = "org.gnome.Mutter.ScreenCast"
SC_ROOT = "/org/gnome/Mutter/ScreenCast"
SC_IFACE = "org.gnome.Mutter.ScreenCast"
SC_SESSION_IFACE = "org.gnome.Mutter.ScreenCast.Session"
SC_STREAM_IFACE = "org.gnome.Mutter.ScreenCast.Stream"

NODE_EVENT = threading.Event()
GST_LOCK = threading.Lock()
NODE_ID = None
RD_PATH = None
SC_PATH = None
STREAM_PATH = None
GST_PROC = None
AUDIO_SOURCE = None
START_TIME = time.time()

BTN_LEFT = 0x110
BTN_RIGHT = 0x111
BTN_MIDDLE = 0x112

KEYSYM = {
    "Backspace": 0xff08,
    "Tab": 0xff09,
    "Enter": 0xff0d,
    "Escape": 0xff1b,
    "Delete": 0xffff,
    "Home": 0xff50,
    "ArrowLeft": 0xff51,
    "ArrowUp": 0xff52,
    "ArrowRight": 0xff53,
    "ArrowDown": 0xff54,
    "PageUp": 0xff55,
    "PageDown": 0xff56,
    "End": 0xff57,
    "Insert": 0xff63,
    "F1": 0xffbe, "F2": 0xffbf, "F3": 0xffc0, "F4": 0xffc1,
    "F5": 0xffc2, "F6": 0xffc3, "F7": 0xffc4, "F8": 0xffc5,
    "F9": 0xffc6, "F10": 0xffc7, "F11": 0xffc8, "F12": 0xffc9,
    "Shift": 0xffe1,
    "Control": 0xffe3,
    "Alt": 0xffe9,
    "Meta": 0xffeb,
    "CapsLock": 0xffe5,
}


def call(bus_name, path, iface, method, params=None):
    return BUS.call_sync(
        bus_name, path, iface, method, params, None,
        Gio.DBusCallFlags.NONE, 5000, None
    )


def get_prop(bus_name, path, iface, prop):
    res = call(
        bus_name, path, "org.freedesktop.DBus.Properties", "Get",
        GLib.Variant("(ss)", (iface, prop))
    )
    return res.unpack()[0]


def create_virtual_monitor():
    global RD_PATH, SC_PATH, STREAM_PATH

    RD_PATH = call(RD_BUS, RD_ROOT, RD_IFACE, "CreateSession").unpack()[0]
    session_id = get_prop(RD_BUS, RD_PATH, RD_SESSION_IFACE, "SessionId")
    print(f"RemoteDesktop session: {RD_PATH}")
    print(f"Session ID: {session_id}")

    props = {"remote-desktop-session-id": GLib.Variant("s", session_id)}
    SC_PATH = call(
        SC_BUS, SC_ROOT, SC_IFACE, "CreateSession",
        GLib.Variant("(a{sv})", (props,))
    ).unpack()[0]
    print(f"ScreenCast session: {SC_PATH}")

    record_props = {
        "is-platform": GLib.Variant("b", True),
        "cursor-mode": GLib.Variant("u", 1),
    }
    STREAM_PATH = call(
        SC_BUS, SC_PATH, SC_SESSION_IFACE, "RecordVirtual",
        GLib.Variant("(a{sv})", (record_props,))
    ).unpack()[0]
    print(f"Virtual stream: {STREAM_PATH}")

    def on_stream_added(connection, sender_name, object_path, interface_name,
                        signal_name, parameters, user_data):
        global NODE_ID
        NODE_ID = parameters.unpack()[0]
        print(f"PipeWire node: {NODE_ID}")
        NODE_EVENT.set()

    BUS.signal_subscribe(
        SC_BUS, SC_STREAM_IFACE, "PipeWireStreamAdded",
        STREAM_PATH, None, Gio.DBusSignalFlags.NONE,
        on_stream_added, None
    )

    call(RD_BUS, RD_PATH, RD_SESSION_IFACE, "Start")
    print("Virtual monitor requested.")


def glib_loop_thread():
    GLib.MainLoop().run()


def pactl_text(*args):
    return subprocess.run(
        ["pactl", *args], check=True, text=True, capture_output=True, timeout=5
    ).stdout.strip()


def list_audio_sources():
    """Enumerate current PipeWire-Pulse sources for the browser dropdown."""
    try:
        short = pactl_text("list", "short", "sources")
    except Exception as e:
        print(f"Audio source enumeration warning: {e}", file=sys.stderr)
        return []

    try:
        default_sink = pactl_text("get-default-sink")
    except Exception:
        default_sink = ""
    try:
        default_source = pactl_text("get-default-source")
    except Exception:
        default_source = ""

    default_monitor = f"{default_sink}.monitor" if default_sink else ""
    items = []
    for line in short.splitlines():
        cols = line.split("\t")
        if len(cols) < 2:
            cols = line.split()
        if len(cols) < 2:
            continue
        name = cols[1].strip()
        if not name:
            continue

        is_monitor = name.endswith(".monitor")
        kind = "system" if is_monitor else "input"
        is_default = name == default_monitor or (not is_monitor and name == default_source)
        label = "System output" if is_monitor else "Microphone / input"
        if is_default:
            label += " (default)"
        items.append({
            "id": name,
            "name": name,
            "label": label,
            "kind": kind,
            "default": is_default,
        })

    items.sort(key=lambda x: (
        0 if x["default"] and x["kind"] == "system" else
        1 if x["kind"] == "system" else
        2 if x["default"] else 3,
        x["name"].lower(),
    ))
    return items


def detect_audio_source():
    requested = REQUESTED_AUDIO.strip()
    if requested.lower() in ("off", "none", "disabled"):
        return None
    sources = list_audio_sources()
    ids = {item["id"] for item in sources}
    if requested and requested != "auto":
        if requested in ids:
            return requested
        raise RuntimeError(f"Requested audio source {requested!r} is unavailable. Run pactl list short sources, or set audio.source=off.")

    for item in sources:
        if item["kind"] == "system" and item["default"]:
            return item["id"]
    for item in sources:
        if item["kind"] == "system":
            return item["id"]
    return None


def build_gstreamer_pipeline(audio_source):
    pipeline = [
        "gst-launch-1.0", "-e",
        "rtspclientsink", "name=s",
        f"location=rtsp://127.0.0.1:8554/{STREAM_NAME}",
        "protocols=tcp",

        "pipewiresrc", f"path={NODE_ID}",
        "!", f"video/x-raw,width={WIDTH},height={HEIGHT},max-framerate={FPS}/1",
        "!", "videoconvert",
        "!", "queue", "max-size-buffers=2", "leaky=downstream",
        "!", "x264enc",
            "tune=zerolatency",
            "speed-preset=ultrafast",
            f"bitrate={BITRATE}",
            f"key-int-max={max(FPS, 1)}",
            "bframes=0",
        "!", "video/x-h264,profile=baseline",
        "!", "h264parse", "config-interval=-1",
        "!", "queue",
        "!", "s.sink_0",
    ]
    if audio_source:
        pipeline += [
            "pulsesrc", f"device={audio_source}", "do-timestamp=true",
            "!", "audioconvert",
            "!", "audioresample",
            "!", "audio/x-raw,rate=48000,channels=2",
            "!", "queue", "max-size-time=2000000000", "leaky=downstream",
            "!", "opusenc", f"bitrate={AUDIO_BITRATE}", "audio-type=generic",
            "!", "queue",
            "!", "s.sink_1",
        ]
    return pipeline


def launch_gstreamer(audio_source):
    global GST_PROC, AUDIO_SOURCE
    print(f"Starting GStreamer publisher from PipeWire node {NODE_ID}...")
    print(f"Video: {WIDTH}x{HEIGHT}, max {FPS} fps, {BITRATE} kbit/s")
    if audio_source:
        print(f"Audio: {audio_source} -> Opus {AUDIO_BITRATE // 1000} kbit/s")
    else:
        print("Audio: OFF (video-only)")

    LOG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_path = LOG_DIR / "gstreamer.log"
    # Keep the log bounded between publisher restarts.
    if log_path.exists() and log_path.stat().st_size > 5_000_000:
        log_path.replace(LOG_DIR / "gstreamer.previous.log")
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as log:
        proc = subprocess.Popen(build_gstreamer_pipeline(audio_source), stdout=log, stderr=subprocess.STDOUT)
    GST_PROC = proc
    time.sleep(2)
    if proc.poll() is not None:
        raise RuntimeError(
            "GStreamer exited during startup. Check PipeWire video negotiation, "
            f"the selected audio source, and MediaMTX. Log: {log_path}"
        )
    GST_PROC = proc
    AUDIO_SOURCE = audio_source


def stop_gstreamer():
    global GST_PROC
    proc = GST_PROC
    GST_PROC = None
    if not proc or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=4)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def start_gstreamer():
    if not NODE_EVENT.wait(10):
        raise RuntimeError("Timed out waiting for Mutter PipeWire node")
    with GST_LOCK:
        launch_gstreamer(detect_audio_source())


def restart_gstreamer(new_source):
    global AUDIO_SOURCE
    with GST_LOCK:
        old_source = AUDIO_SOURCE
        stop_gstreamer()
        time.sleep(0.35)
        try:
            launch_gstreamer(new_source)
        except Exception:
            print("Audio switch failed; restoring previous stream.", file=sys.stderr)
            try:
                launch_gstreamer(old_source)
            except Exception as rollback_error:
                print(f"Rollback failed: {rollback_error}", file=sys.stderr)
            raise

def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("1.1.1.1", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def notify(method, signature=None, args=()):
    params = GLib.Variant(signature, args) if signature else None
    try:
        call(RD_BUS, RD_PATH, RD_SESSION_IFACE, method, params)
    except GLib.Error as e:
        print(f"Input error ({method}): {e}", file=sys.stderr)


def unicode_to_keysym(ch):
    if not ch:
        return None
    cp = ord(ch)
    if cp <= 0xFF:
        return cp
    return 0x01000000 | cp


def key_to_keysym(key):
    if key in KEYSYM:
        return KEYSYM[key]
    if len(key) == 1:
        return unicode_to_keysym(key)
    return None


def send_keysym(ks, down):
    if ks is not None:
        notify("NotifyKeyboardKeysym", "(ub)", (int(ks), bool(down)))




def shutdown():
    global RD_PATH, SC_PATH, STREAM_PATH
    with GST_LOCK:
        stop_gstreamer()
    if RD_PATH:
        try:
            call(RD_BUS, RD_PATH, RD_SESSION_IFACE, "Stop")
        except Exception as exc:
            print(f"Mutter cleanup warning: {exc}", file=sys.stderr)
    RD_PATH = SC_PATH = STREAM_PATH = None
