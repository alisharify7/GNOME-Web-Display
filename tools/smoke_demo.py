#!/usr/bin/env python3
"""Exercise the real launch wrapper, HTTP auth, demo health, and graceful shutdown.
No desktop APIs, Docker, browser navigation, package installation, or sudo.
"""
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    password = secrets.token_urlsafe(24)
    base = f'http://127.0.0.1:{port}'
    env = {k: v for k, v in os.environ.items() if not k.startswith('VSCREEN_')}
    env.update(VSCREEN_PYTHON=sys.executable, VSCREEN_HTTP_PORT=str(port), VSCREEN_PASSWORD=password)
    opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
    with tempfile.TemporaryDirectory() as temporary:
        # A fixed empty config prevents a developer's personal config from changing the test.
        config = Path(temporary) / 'test.toml'
        config.write_text('')
        env['VSCREEN_CONFIG'] = str(config)
        with tempfile.TemporaryFile(mode='w+') as log:
            process = subprocess.Popen(['bash', str(ROOT/'start.sh'), '--demo', '--no-install'],
                                       cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                deadline = time.monotonic()+20
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError('Demo launcher exited before becoming ready')
                    try:
                        with opener.open(base+'/login', timeout=1) as response:
                            assert response.status == 200
                            break
                    except URLError:
                        time.sleep(.1)
                else:
                    raise RuntimeError('Demo startup deadline exceeded')
                try:
                    opener.open(base+'/health', timeout=3)
                    raise AssertionError('Unauthenticated health unexpectedly accessible')
                except HTTPError as exc:
                    assert exc.code == 401
                request = Request(base+'/login', data=urlencode({'username':'display','password':password}).encode(),
                                  headers={'Origin':base, 'Content-Type':'application/x-www-form-urlencoded'})
                with opener.open(request, timeout=3) as response:
                    assert response.status == 200
                    assert b'__STREAM_URL__' not in response.read()
                with opener.open(base+'/health', timeout=3) as response:
                    health = json.load(response)
                    assert health['demo'] is True and health['gstreamer_running'] is False
                    assert health['pipewire_node'] is None
                request = Request(base+'/logout', data=b'', headers={'Origin':base})
                with opener.open(request, timeout=3) as response:
                    assert json.load(response)['ok'] is True
                try:
                    opener.open(base+'/health', timeout=3)
                    raise AssertionError('Signed-out session remained valid')
                except HTTPError as exc:
                    assert exc.code == 401
                process.terminate()
                assert process.wait(timeout=15) == 130
                try:
                    opener.open(base+'/login', timeout=1)
                    raise AssertionError('HTTP server remained after launcher shutdown')
                except URLError:
                    pass
            except Exception:
                log.seek(0)
                print(log.read(), file=sys.stderr)
                raise
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    print('PASS: start.sh --demo --no-install, real HTTP login/session/logout and demo health.')
    print('PASS: SIGTERM cleanup returns 130 and closes the HTTP listener. No desktop or Docker was used.')


if __name__ == '__main__':
    main()
