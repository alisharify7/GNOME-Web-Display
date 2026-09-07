# Validation report - packaged revision 8.0.0

**Date:** 2026-09-07. **Result:** automated application/UI checks passed within the
scope below. Actual GNOME virtual-monitor and physical-device streaming validation
is still required. A final archive is not the same as a hardware-certified release.

## Executed successfully

| Check | Result | Actual scope |
| --- | --- | --- |
| Python unit / HTTP suite | **73 tests passed** | Configuration, secret handling, sessions, rate limits, input protocol, audio-source parsing, pipeline arguments, proxy paths, authentication, cookies, Origin checks, WebSocket/session behavior, and launcher/Docker-version guard logic |
| Real demo launch smoke check | **Passed** | `start.sh --demo --no-install`, actual HTTP login/logout, authentication gate, demo health, SIGTERM and listener cleanup |
| Offline browser UI assertions | **Passed** | Actual HTML/CSS/JS rendered in Chromium with explicit mock Demo responses; no external or localhost navigation |
| Responsive sizes | **Passed** | 320, 360, 390, 430, and 768 px: no horizontal page overflow and key toolbar buttons remain in bounds |
| UI interactions | **Passed** | Focus toggle/drag, fullscreen Focus control, keyboard panel, release-on-pause, and no uncaught JavaScript errors in the exercised flow |
| Screenshot assets | **6 generated and visually inspected** | Desktop dashboard/Focus, mobile display/dashboard/keyboard, desktop sign-in; all media content is Demo |
| Python compilation | **Passed** | All Python files compile under the environment's interpreter |
| Shell syntax | **Passed** | `setup.sh`, `start.sh`, and `run.sh` each checked separately with `bash -n` |
| CLI negative/diagnostic paths | **11 passed** | Version/help, invalid flags/config, missing interpreter, invalid environment value, JSON diagnostics, absent GNOME, missing packages, noninteractive consent, missing password |

The Python test suite uses actual aiohttp local HTTP/WebSocket transports where
appropriate. It does not replace the live GNOME/Docker stack with an unlabelled
fake success. Pure host/launcher unit tests mock the relevant operating-system
operations. Real-host diagnostics correctly report the missing graphical session
in this environment; no package installation or Docker service mutation was done.

The 11 CLI checks were performed in the packaging environment. Their expected
missing-package and missing-session results depend on that environment; use
`tools/smoke_demo.py` and the unit suite for portable repetition.

A text transcript of the passing suite, smoke check, CLI checks, and preview
assertions is included as [test-results.txt](test-results.txt). It contains no real
passwords or captured user desktop content.

## Not validated here

| Area | Why / next step |
| --- | --- |
| Real Mutter `RecordVirtual` and desktop control | No logged-in GNOME Wayland session available; run on the target host |
| GStreamer/PipeWire + MediaMTX media path | No live desktop capture / Docker-backed media session was run |
| Docker Engine networking and image startup | Version checks and arguments are tested, not a running daemon/container; verify externally reachable ports on the actual host |
| APT installation and Docker migration | Only read-only/decline paths executed; review and exercise package transactions on a disposable matching distro |
| Browser navigation end to end | The environment's managed browser blocks localhost navigation; `tools/screenshots.py` could not complete and the policy was not modified |
| Physical phone/tablet keyboard, touch, audio, rotation | Device emulation is not a physical-device test |
| TLS/reverse proxy, Internet/NAT traversal | Configuration support/reference only; deployment testing required |
| Real video performance or audio latency | No measured FPS, end-to-end latency, CPU benchmark, battery test, or quality claim |
| Security review | No independent audit or penetration test; see `SECURITY.md` |
| GitHub Actions | Workflow provided, but not run in the destination repository |

Do not convert these pending items into green compatibility badges or a fabricated
support matrix. The original archive's Debian 13 / GNOME 48 baseline is a useful
starting point, not certification of this revision.

## Repeat the portable checks

Use Python 3.11+ in a development environment with `requirements-dev.txt` installed:

```bash
python -m unittest discover -s tests -v
python tools/smoke_demo.py
python -m compileall -q .
for script in setup.sh start.sh run.sh; do bash -n "$script"; done
python tools/render_preview.py
```

For an actual browser-to-local-server check on a machine that allows it:

```bash
python tools/screenshots.py
```

See [SCREENSHOTS.md](SCREENSHOTS.md) for the precise provenance of the committed
images. Headless browser tooling and its dependencies are for development only;
normal users do not need Playwright.

## Real-host acceptance checklist

Record the distribution, GNOME/Mutter, PipeWire, GStreamer, Docker Engine, image,
GPU/driver, client OS, browser, and network versions with the results.

- [ ] Start from a normal GNOME Wayland terminal. Confirm `--doctor` and a clear
      failure for missing dependencies, inaccessible Docker, or occupied ports.
- [ ] Confirm the additional monitor in GNOME Settings -> Displays. Arrange it,
      move a harmless application onto it, and verify only that monitor is shared.
- [ ] Connect a real desktop browser and physical phone. Check input, touch dragging,
      pointer position at the edges, held-key cleanup, Focus, fullscreen, rotation,
      browser back/reload, and mobile keyboard composition.
- [ ] Verify system-output audio, explicit video-only mode, named-source errors,
      switching sources, unplugging an audio device, autoplay/unmute, and reconnect.
- [ ] Verify login failures/rate limits, session expiry/sign-out, HTTPS/cookie
      settings when enabled, and rejection of wrong-Origin control requests.
- [ ] From another machine, ensure only intended web/UDP ports are reachable;
      `8554` and `8889` must not be reachable directly. Check custom Docker/firewall
      settings, not just the application's intended mappings.
- [ ] Stop with Ctrl+C and confirm that the display, publisher, web listener, and
      only this launcher's container disappear. Test interrupted/failed startup.
- [ ] Repeat on each additional platform before claiming support. Keep sensitive
      screens, device names, IPs, session tokens, and passwords out of public reports.
