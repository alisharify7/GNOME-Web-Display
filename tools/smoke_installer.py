#!/usr/bin/env python3
"""Offline REAL-project clone -> source verification -> demo -> HTTP -> shutdown.

Uses a temporary Git remote and isolated HOME. Does not run setup/APT or Docker.
The release manifest must be current. Root test containers drop install privilege.
"""
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://github.com/alisharify7/GNOME-Web-Display.git'


def main():
    if not shutil.which('git') or sys.platform != 'linux':
        raise SystemExit('Linux and Git are required for this offline smoke test.')
    version = (ROOT / 'VERSION').read_text().strip()
    tag = 'v' + version
    with tempfile.TemporaryDirectory(prefix='gwd-real-install-') as temporary:
        base = Path(temporary)
        seed, remote, home = base / 'seed', base / 'remote.git', base / 'home'
        seed.mkdir()
        home.mkdir()
        # Copy only distributed files, not developer secrets/virtualenvs/artifacts.
        names = [line.split('  ', 1)[1] for line in (ROOT / 'MANIFEST.sha256').read_text().splitlines()]
        for name in [*names, 'MANIFEST.sha256']:
            source = (ROOT / name).resolve()
            if not source.is_relative_to(ROOT) or not source.is_file():
                raise RuntimeError(f'Invalid source manifest path: {name}')
            target = seed / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('VSCREEN_', 'GIT_'))}
        env.update(HOME=str(home), GIT_CONFIG_NOSYSTEM='1',
                   GIT_CONFIG_GLOBAL=str(home / '.gitconfig'))

        def git(*args):
            subprocess.run(['git', *args], env=env, check=True, capture_output=True, text=True)

        git('init', '-q', '-b', 'main', str(seed))
        git('-C', str(seed), 'config', 'user.name', 'Offline Test')
        git('-C', str(seed), 'config', 'user.email', 'test@example.invalid')
        git('-C', str(seed), 'add', '.')
        git('-C', str(seed), 'commit', '-qm', 'Distributed source fixture')
        git('-C', str(seed), 'tag', '-a', tag, '-m', 'Offline test tag')
        git('clone', '-q', '--bare', str(seed), str(remote))
        git('config', '--file', str(home / '.gitconfig'), f'url.file://{remote}.insteadOf', URL)
        identity = {}
        if os.geteuid() == 0:
            identity = dict(user=65534, group=65534, extra_groups=[])
            for path in [base, *base.rglob('*')]:
                if not path.is_symlink():
                    os.chown(path, 65534, 65534)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        password = secrets.token_urlsafe(24)
        env.update(VSCREEN_PYTHON=sys.executable, VSCREEN_PASSWORD=password,
                   VSCREEN_HTTP_PORT=str(port))
        origin = f'http://127.0.0.1:{port}'
        opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
        with tempfile.TemporaryFile(mode='w+') as log:
            process = subprocess.Popen(
                ['bash', str(seed / 'install.sh'), '--version', tag,
                 '--action', 'start', '--demo'],
                cwd=home, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True, **identity,
            )
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError('Installer/server exited early:\n' + log.read())
                    try:
                        with opener.open(origin + '/login', timeout=.5):
                            break
                    except (OSError, URLError):
                        time.sleep(.1)
                else:
                    raise RuntimeError('Installed demo did not become ready.')
                data = urlencode({'username': 'display', 'password': password}).encode()
                with opener.open(Request(origin + '/login', data=data, headers={'Origin': origin}), timeout=3) as response:
                    assert response.status == 200
                    assert version in response.read().decode()
                with opener.open(origin + '/health', timeout=3) as response:
                    health = json.load(response)
                assert health['version'] == version and health['demo'] is True
                assert health['ok'] is True
                process.send_signal(signal.SIGTERM)
                assert process.wait(timeout=15) == 130
                with socket.socket() as sock:
                    sock.settimeout(1)
                    assert sock.connect_ex(('127.0.0.1', port)) != 0
                log.seek(0)
                output = log.read()
                assert 'Source files, SHA-256 manifest and Bash syntax: OK' in output
                assert f'Verified tag + commit: {tag}' in output
                assert 'Running setup.sh' not in output
                installed = home / '.local/share/gnome-web-display/versions' / tag
                # The same verifier must reject a changed source file.
                with (installed / 'web/index.html').open('a') as changed:
                    changed.write('\n<!-- intentional smoke-test corruption -->\n')
                result = subprocess.run(['bash', str(installed / 'scripts/verify.sh'), '--source-only'],
                                        cwd=installed, env=env, capture_output=True, text=True,
                                        timeout=10, **identity)
                assert result.returncode != 0 and 'checksum mismatch' in (result.stdout + result.stderr)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    print(f'PASS: actual {tag} source -> local Git annotated tag -> installer clone -> manifest -> demo startup.')
    print('PASS: installed HTTP login and versioned demo health; SIGTERM exit 130 and listener cleanup.')
    print('PASS: verifier rejects changed frontend source. No public network, APT, Docker or GNOME capture used.')


if __name__ == '__main__':
    main()
