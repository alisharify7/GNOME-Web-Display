#!/usr/bin/env python3
"""Read-only host diagnostics. Standard library only; never invokes sudo."""
from dataclasses import asdict, dataclass
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys

from settings import ROOT, ConfigError, Settings, load_settings


@dataclass
class Finding:
    level: str
    code: str
    message: str
    fix: str = ''


def command(args, timeout=5):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)



def docker_version_issue(version):
    """Reject engines with the documented pre-28 localhost publishing exposure."""
    match = re.match(r'^(\d+)\.', version.strip())
    if not match:
        return 'Cannot determine the Docker Engine server version.'
    if int(match.group(1)) < 28:
        return (f'Docker Engine {version.strip()} is too old: versions before 28.0.0 '
                'can expose localhost-published media ports to the local network.')
    return None


def available_port(host, port, udp=False):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM if udp else socket.SOCK_STREAM) as s:
            s.bind((host, port))
        return True
    except OSError:
        return False


def collect(cfg, demo=False, ports=True):
    result = []
    def add(level, code, message, fix=''):
        result.append(Finding(level, code, message, fix))

    for name in ('app.py', 'host.py', 'index.html', 'login.html', 'settings.py', 'security.py', 'input_protocol.py', 'demo.html', 'mediamtx.yml', 'setup.sh'):
        if not (ROOT / name).is_file():
            add('ERROR', 'file', f'Missing project file: {name}', 'Re-extract the complete release; do not copy only start.sh.')
    add('OK' if sys.version_info >= (3, 11) else 'ERROR', 'python',
        f'Python {platform.python_version()} ({sys.executable})', 'Use Python 3.11+; Debian 13 provides it.')
    modules = ('aiohttp',) if demo else ('aiohttp', 'gi')
    for name in modules:
        rc, text = command([sys.executable, '-c', f'import {name}'])
        add('OK' if rc == 0 else 'ERROR', 'dependency', f'Python module: {name}' + ('' if rc == 0 else ' is missing or broken'),
            'Run bash setup.sh; avoid a virtualenv without --system-site-packages.')
    if not demo:
        if platform.system() != 'Linux':
            add('ERROR', 'session', 'The host must run Linux.', 'Use a GNOME Wayland desktop, not Windows/macOS/WSL/headless SSH.')
        if hasattr(os, 'geteuid') and os.geteuid() == 0:
            add('ERROR', 'session', 'Running as root cannot access your normal graphical session safely.', 'Do not use sudo ./start.sh.')
        if os.environ.get('XDG_SESSION_TYPE') != 'wayland':
            add('ERROR', 'session', 'No Wayland session detected.', 'Log in to GNOME on Wayland and run in its terminal.')
        if not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
            add('ERROR', 'session', 'Graphical-session D-Bus address is missing.', 'Launch from a terminal inside your logged-in GNOME session, not sudo/SSH.')
        required = {'gst-launch-1.0': 'gstreamer1.0-tools', 'gst-inspect-1.0': 'gstreamer1.0-tools',
                    'gdbus': 'libglib2.0-bin', 'ip': 'iproute2', 'docker': 'docker.io', 'pw-cli': 'pipewire-bin'}
        for binary, package in required.items():
            if not shutil.which(binary):
                add('ERROR', 'dependency', f'Missing command: {binary}', f'Run bash setup.sh (Debian package: {package}).')
        if shutil.which('gst-inspect-1.0'):
            plugins = ('pipewiresrc', 'videoconvert', 'queue', 'x264enc', 'h264parse', 'rtspclientsink')
            for element in plugins:
                rc, _ = command(['gst-inspect-1.0', element])
                if rc:
                    add('ERROR', 'dependency', f'Missing GStreamer element: {element}', 'Run bash setup.sh; rtspclientsink requires gstreamer1.0-rtsp.')
            if cfg.audio_source.lower() not in ('off', 'none', 'disabled'):
                for element in ('pulsesrc', 'audioconvert', 'audioresample', 'opusenc'):
                    rc, _ = command(['gst-inspect-1.0', element])
                    if rc:
                        add('ERROR', 'dependency', f'Missing audio element: {element}', 'Run bash setup.sh, or set VSCREEN_AUDIO_SOURCE=off.')
        if shutil.which('gdbus') and os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
            for service in ('RemoteDesktop', 'ScreenCast'):
                rc, text = command(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus',
                                    '--object-path', '/org/freedesktop/DBus', '--method',
                                    'org.freedesktop.DBus.NameHasOwner', f'org.gnome.Mutter.{service}'])
                add('OK' if rc == 0 and 'true' in text.lower() else 'ERROR', 'session',
                    f'Mutter {service} service' + (' is available.' if rc == 0 and 'true' in text.lower() else ' is unavailable.'),
                    'Use a GNOME Wayland session with the Mutter ScreenCast/RemoteDesktop APIs; KDE and X11 are not supported.')
        if shutil.which('pw-cli'):
            rc, _ = command(['pw-cli', 'info', '0'])
            add('OK' if rc == 0 else 'ERROR', 'pipewire',
                'PipeWire is reachable.' if rc == 0 else 'PipeWire is not reachable.',
                'Inspect: systemctl --user status pipewire wireplumber; log out/in after installation.')
        if cfg.audio_source.lower() not in ('off', 'none', 'disabled'):
            rc, _ = command(['pactl', 'info'])
            if rc:
                add('WARN' if cfg.audio_source == 'auto' else 'ERROR', 'audio', 'PipeWire-Pulse audio is unavailable.',
                    'Automatic audio can fall back to video-only. Check pipewire-pulse or set VSCREEN_AUDIO_SOURCE=off.')
        if shutil.which('docker'):
            rc, version = command(['docker', 'info', '--format', '{{.ServerVersion}}'])
            add('OK' if rc == 0 else 'WARN', 'docker',
                'Docker daemon is accessible.' if rc == 0 else 'Docker needs permission or its daemon is stopped.',
                'The launcher can ask to use sudo for Docker; it never adds you to the root-equivalent docker group.')
            if rc == 0 and (issue := docker_version_issue(version)):
                add('ERROR', 'docker-version', issue,
                    'Upgrade the server to Docker Engine 28+ using the official distribution-specific instructions linked in README.md. No Docker repositories are changed automatically.')
        for name, threshold in [('max_user_instances', 1024), ('max_user_watches', 524288)]:
            try:
                value = int(Path('/proc/sys/fs/inotify', name).read_text())
                if value < threshold:
                    add('WARN', 'inotify', f'inotify {name}={value}; heavily loaded desktops may exhaust it.',
                        'Only if logs report inotify exhaustion: see README.md. No kernel settings are changed automatically.')
            except (OSError, ValueError):
                pass
    if ports:
        endpoints = [(cfg.http_host, cfg.http_port, False)]
        if not demo:
            endpoints += [('127.0.0.1', 8554, False), ('127.0.0.1', 8889, False), ('0.0.0.0', 8189, True)]
        for host, port, udp in endpoints:
            ok = available_port(host, port, udp)
            proto = 'UDP' if udp else 'TCP'
            add('OK' if ok else 'ERROR', 'port', f'{proto} {host}:{port} ' + ('is free.' if ok else 'is occupied or cannot be bound.'),
                'Stop the process using this port. For the dashboard, change [server].port in config.toml.')
    return result


def print_report(findings, json_output=False):
    if json_output:
        print(json.dumps({'ok': not any(x.level == 'ERROR' for x in findings),
                          'checks': [asdict(x) for x in findings]}, indent=2))
    else:
        for item in findings:
            print(f'[{item.level:5}] {item.message}')
            if item.fix and item.level != 'OK':
                print(f'        Fix: {item.fix}')
        errors = sum(x.level == 'ERROR' for x in findings)
        warnings = sum(x.level == 'WARN' for x in findings)
        print(f'\nResult: {errors} error(s), {warnings} warning(s). No system settings were changed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--demo', action='store_true', help='Check the browser preview only.')
    args = parser.parse_args()
    try:
        cfg = load_settings(args.config)
        if args.demo:
            cfg.http_host = '127.0.0.1'
        findings = collect(cfg, args.demo)
    except ConfigError as exc:
        findings = [Finding('ERROR', 'config', str(exc))]
    print_report(findings, args.json)
    return int(any(x.level == 'ERROR' for x in findings))


if __name__ == '__main__':
    raise SystemExit(main())
