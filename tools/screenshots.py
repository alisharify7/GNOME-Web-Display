#!/usr/bin/env python3
"""Capture the real UI in demo mode. Requires Playwright + a Chromium browser.
Starts its own loopback-only server with an ephemeral password; never captures a desktop.
"""
import argparse
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    from playwright.sync_api import sync_playwright
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/images')
    parser.add_argument('--browser', default=shutil.which('chromium') or shutil.which('google-chrome'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    password = secrets.token_urlsafe(24)
    env = {k: v for k, v in os.environ.items() if not k.startswith('VSCREEN_')}
    env.update(VSCREEN_PASSWORD=password, VSCREEN_HTTP_PORT=str(port), VSCREEN_USER='display')
    env['PYTHONPATH'] = str(ROOT / 'src') + os.pathsep + env.get('PYTHONPATH', '')
    server = subprocess.Popen([sys.executable, '-m', 'gnome_web_display.app', '--demo'], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    origin = f'http://127.0.0.1:{port}'
    errors = []
    try:
        for _ in range(80):
            if server.poll() is not None:
                raise RuntimeError(server.stderr.read().decode())
            try:
                urllib.request.urlopen(origin + '/login', timeout=.2).close()
                break
            except (OSError, urllib.error.URLError):
                time.sleep(.1)
        else:
            raise RuntimeError('Preview server did not start')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path=args.browser,
                                                  args=['--no-sandbox'])
            context = browser.new_context(viewport={'width': 1440, 'height': 960}, device_scale_factor=1)
            page = context.new_page()
            page.on('pageerror', lambda err: errors.append(str(err)))
            page.goto(origin + '/login')
            page.screenshot(path=str(args.output / 'login-desktop.png'))
            page.fill('#password', password)
            page.click('button[type=submit]')
            page.wait_for_url(origin + '/')
            page.wait_for_selector('#statusText:text("Demo")')
            page.wait_for_timeout(1200)
            page.screenshot(path=str(args.output / 'desktop-dashboard.png'))
            # Check actual controls rather than changing CSS to stage screenshots.
            page.click('#keyboardBtn')
            page.wait_for_timeout(250)
            assert 'hidden' not in page.locator('#keyboardPanel').get_attribute('class')
            page.click('#closeKeyboard')
            page.click('#focusFab')
            page.wait_for_timeout(1800)
            assert 'focus-mode' in page.locator('body').get_attribute('class')
            page.screenshot(path=str(args.output / 'desktop-focus.png'))
            page.click('#focusFab')
            # Fullscreen keeps Focus inside the element entering fullscreen.
            page.click('#fullscreenBtn')
            page.wait_for_timeout(250)
            assert page.evaluate("document.fullscreenElement?.id === 'stage'")
            assert page.locator('#focusFab').is_visible()
            page.click('#fullscreenBtn')
            # Blocked storage must not break dragging/clicking Focus.
            page.evaluate("Storage.prototype.setItem = function(){throw new Error('blocked storage')}")
            page.click('#focusFab')
            page.click('#focusFab')
            mobile = browser.new_context(viewport={'width': 430, 'height': 932}, device_scale_factor=1,
                                         is_mobile=True, has_touch=True)
            m = mobile.new_page()
            m.on('pageerror', lambda err: errors.append(str(err)))
            m.goto(origin + '/login')
            m.fill('#password', password)
            m.click('button[type=submit]')
            m.wait_for_url(origin + '/')
            m.wait_for_timeout(1200)
            assert 'hidden' in m.locator('#dashboard').get_attribute('class')
            m.screenshot(path=str(args.output / 'mobile-display.png'))
            m.click('#dashboardBtn')
            m.wait_for_timeout(300)
            m.screenshot(path=str(args.output / 'mobile-dashboard.png'))
            m.click('#keyboardBtn')
            m.wait_for_timeout(300)
            assert 'hidden' in m.locator('#dashboard').get_attribute('class')
            m.screenshot(path=str(args.output / 'mobile-keyboard.png'))
            # The browser emulator does not emulate an Android/iOS software keyboard.
            for width in (320, 360, 390, 430, 768):
                m.set_viewport_size({'width': width, 'height': 932})
                m.wait_for_timeout(80)
                assert m.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Overflow at {width}px'
                for button in ('audioBtn', 'keyboardBtn', 'dashboardBtn', 'fullscreenBtn', 'logoutBtn'):
                    bounds = m.locator('#' + button).bounding_box()
                    assert bounds and bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width + 1, (width, button, bounds)
            page.click('#logoutBtn')
            page.wait_for_url(origin + '/login')
            assert not context.cookies() or not any(c['name'] == 'gwd_session' for c in context.cookies())
            browser.close()
        if errors:
            raise AssertionError('Browser JavaScript errors: ' + '; '.join(errors))
        print('Browser checks passed: login, dashboard, keyboard, Focus, fullscreen, storage fallback, responsive widths, logout.')
        print('Screenshots are real browser renders of Demo mode, NOT a GNOME streaming benchmark.')
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill(); server.wait()
        server.stderr.close()


if __name__ == '__main__':
    main()
