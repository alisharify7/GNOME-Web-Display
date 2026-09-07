# Screenshot provenance

All six committed PNGs (regenerated for v2.0.0) are browser-rendered captures of this repository's actual
HTML/CSS/JavaScript. They were produced with `tools/render_preview.py` using
headless Chromium and Playwright. They were not generated with an image model and
are not photographs of physical devices.

The host environment had no usable GNOME Wayland session or physical phone.
Browser navigation to localhost was also blocked by an environment policy. The
policy was not changed or bypassed: the preview renderer uses `page.set_content`
with the real UI, a `srcdoc` containing `web/demo.html`, and explicit mock health and
WebSocket responses. It does not navigate to a server or contact MediaMTX.

Every display preview visibly identifies itself as a Demo. The sample workspace
inside the virtual display is HTML/CSS demonstration content, not a captured
Linux desktop. The login image is only a render of `web/login.html`; it is not evidence
of authentication. Real authentication is covered separately by HTTP tests.

| File | Viewport | What it shows |
| --- | --- | --- |
| `images/desktop-dashboard.png` | 1440 x 960 | Actual desktop UI and metrics panel with demo data |
| `images/desktop-focus.png` | 1440 x 960 | Actual Focus layout and floating control |
| `images/mobile-display.png` | 430 x 932 | Responsive mobile viewer layout |
| `images/mobile-dashboard.png` | 430 x 932 | Responsive dashboard drawer |
| `images/mobile-keyboard.png` | 430 x 932 | In-app keyboard panel, not the phone's native keyboard |
| `images/login-desktop.png` | 1440 x 960 | Actual sign-in page template, no real password |

## Reproduce the committed previews

From the repository root, inside a development environment:

```bash
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python tools/render_preview.py
```

The tool can use system Chromium or the Playwright browser. Specify another
executable with `--browser /path/to/chromium`, or write to a different directory
with `--output /path/to/previews`.

It also asserts Focus toggling/dragging, fullscreen control placement, keyboard
visibility, release-on-pause, absence of uncaught JavaScript errors, and toolbar
fit at 320, 360, 390, 430, and 768 px. These are UI checks, not device certification
or measurements of video FPS, latency, battery use, or audio quality.

## Browser navigation against a real local demo server

On a machine whose browser permits localhost navigation:

```bash
python tools/screenshots.py
```

This alternate harness launches the actual authenticated Demo server with an
ephemeral password and port. It is supplied for further end-to-end browser checks;
it could not complete in the packaging environment due to the policy described
above. The generated content is still Demo, not live GNOME capture.

## Replace previews with actual usage captures

Use a real GNOME Wayland host, start `bash start.sh`, connect a desktop browser
and a physical phone, and move non-sensitive content onto the virtual monitor.
Capture the real client views with consent, redact private content, and add the
host/browser/device versions and date to this file. Remove Demo claims only for
images actually replaced; do not relabel these existing demo assets as live capture.
