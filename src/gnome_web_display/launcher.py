#!/usr/bin/env python3
"""Interactive startup with explicit consent and cleanup limited to our container."""
import argparse
import fcntl
import getpass
import json
import os
from pathlib import Path
import shlex
import signal
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

from .paths import CONFIG_ROOT
from .doctor import collect, command, docker_version_issue, print_report
from .settings import ROOT, VERSION, ConfigError, load_settings, read_password


class LaunchError(RuntimeError):
    pass


def consent(question, yes=False):
    if yes:
        return True
    if not sys.stdin.isatty():
        return False
    try:
        return input(question + ' [y/N] ').strip().lower() in ('y', 'yes')
    except EOFError:
        return False


def run_checked(args, **kwargs):
    try:
        subprocess.run(args, check=True, **kwargs)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise LaunchError(f'Command failed: {shlex.join(args)}. {exc}') from None


def networks():
    rc, output = command(['ip', '-j', '-4', 'address', 'show', 'up'])
    if rc:
        raise LaunchError('Cannot list IPv4 interfaces. Install iproute2 and check `ip -4 addr`.')
    try:
        choices = []
        for interface in json.loads(output):
            name = interface['ifname']
            if name.startswith(('lo', 'docker', 'br-', 'veth', 'virbr', 'podman')):
                continue
            for address in interface.get('addr_info', []):
                if address.get('family') == 'inet' and address.get('scope') == 'global':
                    choices.append((name, address['local']))
        return choices
    except (ValueError, KeyError, TypeError):
        raise LaunchError('Unexpected `ip -j` response; set network.advertised_ip in config.toml.') from None


def choose_ip(cfg):
    if cfg.advertised_ip:
        return cfg.advertised_ip
    choices = networks()
    if cfg.interface:
        choices = [item for item in choices if item[0] == cfg.interface]
    if not choices:
        raise LaunchError('No usable IPv4 interface. Connect to your LAN or set network.advertised_ip.')
    if len(choices) == 1:
        name, address = choices[0]
        print(f'Network: {name} -> {address}')
        return address
    if not sys.stdin.isatty():
        raise LaunchError('Several network interfaces found. Set network.interface or network.advertised_ip for unattended startup.')
    print('Select the interface reachable by your second device:')
    for i, (name, address) in enumerate(choices, 1):
        print(f'  {i}) {name:16} {address}')
    print('  0) Cancel')
    while True:
        value = input('Selection: ').strip()
        if value == '0':
            raise LaunchError('Cancelled; nothing started.')
        if value.isdigit() and 1 <= int(value) <= len(choices):
            return choices[int(value)-1][1]
        print('Please select one of the listed numbers.')


def docker_command(yes):
    if command(['docker', 'info'], timeout=6)[0] == 0:
        return ['docker']
    if consent('Docker is unavailable to this user. Try Docker with sudo for this run?', yes):
        # Inherit the terminal so the sudo password prompt stays visible.
        run_checked(['sudo', '-v'])
        if command(['sudo', '-n', 'docker', 'info'], timeout=6)[0] == 0:
            return ['sudo', 'docker']
        if consent('Docker is stopped. Run sudo systemctl start docker?', yes):
            run_checked(['sudo', 'systemctl', 'start', 'docker'])
            if command(['sudo', 'docker', 'info'], timeout=10)[0] == 0:
                return ['sudo', 'docker']
    raise LaunchError('Docker is not accessible. Check `sudo systemctl status docker` and run again. Group membership was not changed.')



def require_safe_docker(docker):
    rc, version = command(docker + ['info', '--format', '{{.ServerVersion}}'])
    issue = docker_version_issue(version) if rc == 0 else 'Cannot read the Docker Engine server version.'
    if issue:
        raise LaunchError(issue + ' Upgrade Docker Engine to 28+; see README.md. No image or container was created.')


def mediamtx_config_for_container():
    """Make the public bundled config readable across Docker user namespaces."""
    path = CONFIG_ROOT / 'mediamtx.yml'
    try:
        details = path.lstat()
        if not stat.S_ISREG(details.st_mode):
            raise LaunchError(f'Bundled MediaMTX config is not a regular file: {path}')
        mode = stat.S_IMODE(details.st_mode)
        if mode & 0o444 != 0o444:
            path.chmod(mode | 0o444)
    except OSError as exc:
        raise LaunchError(f'Cannot make the bundled MediaMTX config readable: {path}. {exc}') from None
    return path


def wait_mediamtx(docker, container, seconds=20):
    deadline = time.monotonic() + seconds
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        rc, state = command(docker + ['inspect', '-f', '{{.State.Running}}', container])
        if rc or state != 'true':
            break
        try:
            with opener.open('http://127.0.0.1:8889/', timeout=1):
                return
        except urllib.error.HTTPError:
            return  # Any HTTP response proves that the private listener is ready.
        except (OSError, urllib.error.URLError):
            time.sleep(.3)
    _, logs = command(docker + ['logs', '--tail', '60', container])
    raise LaunchError('MediaMTX did not become ready. Recent logs:\n' + logs)


def main():
    parser = argparse.ArgumentParser(description='GNOME Web Display - browser-based second monitor for GNOME Wayland')
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('--config', help='Read a particular TOML file.')
    parser.add_argument('--doctor', action='store_true', help='Read-only diagnostics; never install or launch.')
    parser.add_argument('--json', action='store_true', help='JSON diagnostics (with --doctor).')
    parser.add_argument('--yes', action='store_true', help='Explicitly approve installation/service prompts; never supplies a password or picks a network.')
    parser.add_argument('--no-install', action='store_true', help='Fail with repair commands rather than offering package installation.')
    parser.add_argument('--demo', action='store_true', help='Local-only UI preview; no monitor, audio, Docker or remote input.')
    parser.add_argument('--update-image', action='store_true', help='Explicitly pull the configured MediaMTX image even if cached.')
    args = parser.parse_args()
    cfg = load_settings(args.config)
    if args.demo:
        cfg.http_host = '127.0.0.1'
        cfg.public_origin = ''
        cfg.tls_cert = cfg.tls_key = ''
    checks = collect(cfg, args.demo)
    if args.doctor:
        print_report(checks, args.json)
        return int(any(x.level == 'ERROR' for x in checks))
    if args.json:
        parser.error('--json requires --doctor')
    print(f'GNOME Web Display {VERSION}', flush=True)
    print_report(checks)
    errors = [x for x in checks if x.level == 'ERROR']
    # Never install packages in response to the wrong desktop or occupied ports.
    if any(x.code != 'dependency' for x in errors):
        raise LaunchError('Resolve the errors above, then run ./start.sh again. Use --doctor to re-check.')
    if errors:
        if args.no_install or not consent('Required packages are missing. Run the Debian/Ubuntu installer?', args.yes):
            raise LaunchError('Dependencies are missing. Run bash setup.sh, or ./start.sh --yes to explicitly approve installation.')
        run_checked(['bash', str(ROOT / 'setup.sh')] + (['--yes'] if args.yes else []))
        checks = collect(cfg, args.demo)
        if any(x.level == 'ERROR' for x in checks):
            print_report(checks)
            raise LaunchError('Setup finished but runtime checks still fail. Log out/in if PipeWire was just installed.')
    password = read_password(cfg)
    if not password:
        if not sys.stdin.isatty():
            raise LaunchError('No terminal to ask for a password. Set auth.password_file (mode 600) or VSCREEN_PASSWORD.')
        while True:
            password = getpass.getpass('Browser password (8-1024 characters): ')
            if not 8 <= len(password) <= 1024:
                print('Use 8-1024 characters.'); continue
            if getpass.getpass('Confirm password: ') == password:
                break
            print('Passwords do not match.')
    advertised = '127.0.0.1' if args.demo else choose_ip(cfg)
    if not args.demo and cfg.http_host == '127.0.0.1':
        print('NOTICE: Dashboard is loopback-only. A second device needs an HTTPS reverse proxy or an appropriate host binding.')
    env = os.environ.copy()
    env['VSCREEN_PASSWORD'] = password
    env['VSCREEN_ADVERTISED_IP'] = advertised
    child = None
    docker = None
    container_id = None
    lock_file = None
    def stop_signal(signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop_signal)
    try:
        if not args.demo:
            # Advisory per-user lock prevents concurrent launchers racing on fixed media ports.
            runtime = Path(os.environ.get('XDG_RUNTIME_DIR', str(Path.home() / '.cache')))
            runtime.mkdir(parents=True, exist_ok=True)
            lock_file = open(runtime / 'gnome-web-display.lock', 'a')
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise LaunchError('Another GNOME Web Display launcher is already running.') from None
            docker = docker_command(args.yes)
            require_safe_docker(docker)
            if args.update_image or command(docker + ['image', 'inspect', cfg.mediamtx_image])[0]:
                print(f'Pulling {cfg.mediamtx_image} (network access required)...', flush=True)
                run_checked(docker + ['pull', cfg.mediamtx_image])
            else:
                print('Using cached MediaMTX image; no pull needed.')
            name = f'gnome-web-display-{os.getuid()}-{os.getpid()}'
            media_config = mediamtx_config_for_container()
            # Create first, so even interrupted starts can clean up ONLY this instance.
            cmd = docker + ['create', '--name', name, '--label', 'app=gnome-web-display',
                '--cap-drop=ALL', '--security-opt', 'no-new-privileges:true',
                '--mount', f'type=bind,src={media_config},dst=/mediamtx.yml,readonly',
                '-e', f'MTX_WEBRTCADDITIONALHOSTS={advertised}',
                '-p', '127.0.0.1:8554:8554/tcp', '-p', '127.0.0.1:8889:8889/tcp',
                '-p', '8189:8189/udp', cfg.mediamtx_image, '/mediamtx.yml']
            rc, result = command(cmd, timeout=30)
            if rc:
                raise LaunchError('Could not create MediaMTX container:\n' + result)
            container_id = result.splitlines()[-1]
            run_checked(docker + ['start', container_id], stdout=subprocess.DEVNULL)
            wait_mediamtx(docker, container_id)
        scheme = 'https' if cfg.tls_cert else 'http'
        url = cfg.public_origin or f'{scheme}://{advertised}:{cfg.http_port}'
        print(f'\nStarting server. Browser URL: {url}\nUsername: {cfg.user}', flush=True)
        if not cfg.tls_cert and not cfg.public_origin.startswith('https:'):
            print('WARNING: HTTP does not protect your password/input on the network. Use only a trusted LAN or an encrypted VPN.', flush=True)
        child_args = [sys.executable, '-u', '-m', 'gnome_web_display.app']
        if args.config:
            child_args += ['--config', str(Path(args.config).resolve())]
        if args.demo:
            child_args += ['--demo']
        child = subprocess.Popen(child_args, env=env, start_new_session=True)
        return child.wait()
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        if container_id and docker:
            print('Stopping this instance of MediaMTX...', flush=True)
            command(docker + ['rm', '-f', container_id], timeout=15)
        if lock_file:
            lock_file.close()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\nStopped.'); raise SystemExit(130)
    except (ConfigError, LaunchError, OSError, EOFError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(2)
