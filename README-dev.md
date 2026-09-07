# GNOME Web Display — developer guide

This document covers the internals of **v8.0.0**, prepared from the supplied v7.1
archive. End-user installation and controls belong in [README.md](README.md).

The project is a small, single-host/single-monitor application, not a multi-tenant
remote-desktop platform. Keep the implementation understandable and preserve the
separation between local desktop access and untrusted browser requests.

## Architecture

```text
GNOME / Mutter                           Browser client
  |                                          |
  | private session D-Bus                     | login + cookie
  v                                          | HTTP(S) / WebSocket
host.py <----- validated input ----- app.py <-+
  |                                  |        |
  | RecordVirtual                    |        | same-origin iframe
  v                                  |        v
PipeWire node                        +---- /stream/... WHEP proxy
  |                                           |
  v                                           v
GStreamer: x264 + optional Opus ---- RTSP --> MediaMTX container
                                   8554       8889 signaling (private)
                                                |
                                                +--- UDP 8189 ---> Browser video
```

`start.sh` selects a Python interpreter and hands off to `launcher.py`.
`launcher.py` validates settings, runs diagnostics, manages an isolated media
container, and supervises the application child. `app.py` owns authenticated HTTP,
WebSocket input, and the local-only demo. `host.py` retains the Mutter/PipeWire/
GStreamer capture approach from v7.1 with safer startup, audio handling, and cleanup.

The Mutter APIs used here are **private** and do not promise cross-version
compatibility. A different GNOME version needs a real-host test; package installation
alone does not prove support. [Mutter's interface definition][mutter-sc] documents
`RecordVirtual`, cursor modes, and the linked remote-desktop session.

## Repository map

```text
.
├── README.md                   User-facing installation, controls and troubleshooting
├── README-dev.md               This document
├── CHANGELOG.md                Release changes
├── SECURITY.md                 Threat model and operational limitations
├── LICENSE-NOTICE.md            Missing upstream license disclosure
├── config.example.toml         Full, commented configuration example
├── settings.py                 TOML/environment parsing and validation
├── start.sh / run.sh            Entry point and compatibility wrapper
├── setup.sh                    Consent-based Debian/Ubuntu dependency installer
├── launcher.py                 Preflight, network selection, Docker supervision
├── doctor.py                   Read-only text/JSON diagnostics
├── app.py                      aiohttp application and session-protected gateway
├── security.py                 Bounded session store and sign-in limiter
├── input_protocol.py           Input validation and held-key/button state
├── host.py                     Lazy GI initialization, capture and audio publisher
├── index.html / login.html     Real browser UI and sign-in page
├── demo.html                   Explicitly synthetic preview workspace
├── mediamtx.yml                Read-only-mounted media configuration
├── tests/                      Unit and in-process HTTP/WebSocket integration tests
├── tools/screenshots.py        Optional real localhost demo browser smoke test
├── tools/render_preview.py     Offline UI renderer with demo/mock network data
├── docs/                       Screenshot provenance and validation report
└── .github/workflows/ci.yml    Python, shell and browser-preview checks
```

No frontend bundler, CDN assets, external font dependency, or Node package install
is required to run the app. The browser code is kept inline in `index.html`.

## Development environment

### Real capture on the target desktop

Use a regular terminal in a GNOME Wayland session:

```bash
bash setup.sh
bash start.sh --doctor
bash start.sh
```

The supported installer path is APT. Core packages include `python3-aiohttp`,
`python3-gi`, `gir1.2-glib-2.0`, `libglib2.0-bin`, PipeWire and PipeWire-Pulse,
`pulseaudio-utils`, `iproute2`, and the GStreamer tools/plugins listed in `setup.sh`.
In particular, Debian packages `rtspclientsink` in [`gstreamer1.0-rtsp`][debian-rtsp].
An existing Docker CE installation is respected; `docker.io` is offered only when
no `docker` command is found.

The launcher deliberately defaults to `/usr/bin/python3` so distribution GI
bindings remain visible. To use another interpreter explicitly:

```bash
VSCREEN_PYTHON=/path/to/python3 bash start.sh
```

For an isolated environment with desktop bindings, create it using the distribution
Python and `--system-site-packages`. Installing `gi` with a random similarly named
PyPI package is not the intended setup path.

### UI and backend development without GNOME

Python 3.11+ and aiohttp are sufficient for demo mode and the automated tests:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
VSCREEN_PYTHON="$PWD/.venv/bin/python" bash start.sh --demo
```

`requirements-dev.txt` is a bounded development dependency list, not a deployment
lockfile. Production host packages are managed by the distribution. The demo
binds loopback only even when configuration asks for a LAN bind. It has no desktop
permission or real audio/video media. Authentication remains enabled.

## Configuration reference

TOML values are checked before the desktop is touched. Defaults are in
`settings.Settings`. Environment variables override TOML. The normal file is
`config.toml` beside the source; explicit `--config` takes priority over
`VSCREEN_CONFIG`. File paths in TOML are resolved relative to the selected file.

| TOML key | Environment | Default / unit |
| --- | --- | --- |
| `display.width` | `VSCREEN_WIDTH` | `1920`, pixels; even, 256–7680 |
| `display.height` | `VSCREEN_HEIGHT` | `1080`, pixels; even, 144–4320 |
| `display.fps` | `VSCREEN_FPS` | `60`, target frames/s; 1–120 |
| `display.bitrate_kbps` | `VSCREEN_BITRATE` | `6000`, kbit/s; 128–100000 |
| `audio.source` | `VSCREEN_AUDIO_SOURCE` | `auto`, `off`, or an exact source name |
| `audio.bitrate_bps` | `VSCREEN_AUDIO_BITRATE` | `128000`, bit/s; 6000–510000 |
| `server.host` | `VSCREEN_HTTP_HOST` | `0.0.0.0`, IPv4 listen address |
| `server.port` | `VSCREEN_HTTP_PORT` | `8090`; 1024–65535 except media TCP ports |
| `server.stream_name` | `VSCREEN_STREAM_NAME` | `monitor`; 1–64 letters/digits/`_`/`-` |
| `server.public_origin` | `VSCREEN_PUBLIC_ORIGIN` | empty; exact reverse-proxy origin, no path |
| `server.tls_cert` | `VSCREEN_TLS_CERT` | empty; native TLS certificate path |
| `server.tls_key` | `VSCREEN_TLS_KEY` | empty; native TLS private key path |
| `network.advertised_ip` | `VSCREEN_ADVERTISED_IP` | empty; choose an address interactively |
| `network.interface` | `VSCREEN_INTERFACE` | empty; filter auto-detection by interface |
| `mediamtx.image` | `VSCREEN_MEDIAMTX_IMAGE` | `bluenviron/mediamtx:1.21.0` |
| `auth.username` | `VSCREEN_USER` | `display` |
| `auth.password_file` | `VSCREEN_PASSWORD_FILE` | empty; private UTF-8 file, owned by user |
| `auth.session_hours` | `VSCREEN_SESSION_HOURS` | `12`; 1–72 hours |
| No TOML password key | `VSCREEN_PASSWORD` | unset; prompt or private file |

These are validation limits, not guarantees that a particular GPU, codec, client,
or compositor can achieve every combination. The H.264 baseline software-encoding
path is retained; no hardware-encoding fallback or measured latency guarantee is
implemented.

The internal media ports are intentionally fixed. To change them, update the Docker
mapping, `mediamtx.yml`, diagnostics, `host.py`, and `app.py` together and add tests.

## Startup and shutdown behavior

The normal sequence is: validate configuration → read-only diagnostics → optional
consented dependency installation → password resolution → network selection →
per-user launch lock → Docker permission/version check → cached image/pull → create and
start a unique container → HTTP readiness probe → start application child.

A unique container name includes UID and launcher PID. Cleanup addresses only the
returned container ID. The launcher does **not** remove an existing v7.1 container
or unrelated service to free a port. On a crash/power failure/SIGKILL, inspect stale
containers manually. The launcher lock is advisory and does not reserve every
network port; bind/start errors still need handling.

The application starts a GLib loop, requests the linked Mutter remote-desktop and
screen-cast sessions, waits for the PipeWire node, and starts GStreamer. Resource
cleanup covers startup failures as well as normal shutdown. A dying publisher is
reported through `/health`; there is no unlimited automatic restart loop.

GStreamer logs are appended under the user's state directory. On a subsequent
publisher start, a file larger than 5 MB is moved to `gstreamer.previous.log`.
This is **restart-time rotation**, not a strict running-process disk quota.

## MediaMTX integration

`mediamtx.yml` is actually mounted into the container, read-only. v7.1 shipped a
configuration file that its launcher did not mount. v8 also disables unused media
protocols/services and pins an image version instead of using the floating `:1` tag.

The host publishes only TCP `8554` and `8889` on loopback, plus UDP `8189` for media.
`MTX_WEBRTCADDITIONALHOSTS` supplies the selected client-reachable IPv4 address.
The launcher requires Docker Engine **28.0.0+**, including when using `sudo docker`,
and fails before pulling/creating a container if the server version is older or
unreadable. This avoids the documented pre-28 localhost-published-port exposure.
The installer will not switch Docker repositories or replace Docker CE automatically;
a separately reviewed Engine upgrade may be required after installing `docker.io`.
Docker creates publishing/NAT rules, even though the project does not invoke
UFW/iptables or change firewall policy itself. Host processes and other containers
on the same Docker bridge remain trusted. See [Docker's port-publishing docs][docker-ports].

Container interface discovery is disabled to avoid advertising an unusable Docker
bridge address. These configuration mechanisms are described by
[MediaMTX's configuration documentation][mtx-config].

The checked source schema is [MediaMTX v1.21.0's configuration][mtx-schema]. The
binary/container itself was not executed in this packaging environment. A pinned
tag helps control compatibility, but is not a digest pin or a claim of supply-chain
verification. Review upstream security updates and validate any replacement image.

`app.py` reuses one aiohttp client session, ignores ambient HTTP proxy variables,
limits request bodies, blocks arbitrary proxy paths/WHIP publishing, rewrites
local WHEP `Location` headers, and reports upstream failures as `502`.
The allowed browser resources are:

```text
/stream/<configured-name>/
/stream/<configured-name>/reader.js
/stream/<configured-name>/whep
/stream/<configured-name>/whep/<session-uuid>
```

This matches the checked [MediaMTX HTTP routing][mtx-http] and
[built-in reader page][mtx-reader]. A future upstream change to player resources or
WHEP paths needs proxy and integration-test updates.

## HTTP API

All endpoints except sign-in and the empty favicon response require the session
cookie. Cross-origin writes and WebSocket upgrades are rejected. Mutating requests
must include an `Origin` exactly matching the application's origin, or the explicit
`server.public_origin` behind a reverse proxy. This applies to command-line clients
as well as browsers; missing `Origin` is not silently accepted.

| Method and path | Purpose |
| --- | --- |
| `GET /login` | Sign-in form |
| `POST /login` | Form fields `username`, `password`; successful login redirects to `/` |
| `POST /logout` | Revoke this token and close associated input sockets |
| `GET /` | Render dashboard with escaped username and validated display settings |
| `GET /health` | JSON publisher/configuration state; contains `demo: true` in preview |
| `GET /api/audio-sources` | List host sources and the current selection |
| `POST /api/audio-source` | JSON `{"source":"off"}` or an exact source ID |
| `GET /ws` | Same-origin, authenticated input WebSocket |
| `GET /demo-screen` | Protected synthetic page, available only in demo mode |
| `/stream/...` | Restricted WHEP/player gateway |

`/health` remains HTTP `200` when an authenticated host-status response can be
produced; inspect JSON `ok` and `gstreamer_running`. A stopped publisher sets
`ok: false` in live mode. In Demo, `ok: true` means the **preview server**, not the
media pipeline, is available.

Status classes include `400` malformed input, `401` unauthenticated/bad login,
`403` origin rejected, `409` unavailable demo operation, `413` oversized HTTP body,
`429` sign-in throttling, `502` media upstream failure, and `503` failed audio switch.
Errors may be plain text or JSON; client code must not assume every error is JSON.

### WebSocket messages

```json
{"type":"move","x":400,"y":300}
{"type":"button","button":0,"down":true}
{"type":"button","button":0,"down":false}
{"type":"wheel","dx":0,"dy":120}
{"type":"key","key":"Control","down":true}
{"type":"key","key":"Control","down":false}
{"type":"text","text":"Hello"}
{"type":"release"}
{"type":"ping","ts":12345.67}
```

Button IDs are `0` left, `1` middle, `2` right. Pointer coordinates are clamped to
configured dimensions and must be finite numbers. `down` must be a JSON boolean.
Text messages are limited to 256 Unicode characters. Messages are limited to 8 KB;
each socket is capped at 600 messages per one-second window. Invalid messages
receive an error where practical. `ping` returns `pong` with the caller's timestamp.

Each live socket tracks held keys/buttons and releases them on explicit release
or disconnect. The client releases input on pause, window blur, page hiding, and
pointer cancellation. Pointer motion is coalesced to animation frames. Multiple
controllers still share one host seat; there is no ownership arbitration and one
client's releases can interact with another's input. Prefer one active controller.

Unicode keysyms are not clipboard synchronization. Advanced IME behavior and some
reserved OS shortcuts remain platform/browser dependent.

## Authentication and security boundaries

The application has one configured account, not a user database. Tokens are random,
per-login, in-memory, server-expiring, and bounded to 32 sessions. Cookies use
HttpOnly and SameSite=Strict, plus Secure for native HTTPS or an explicitly configured
HTTPS public origin. Restarting the application invalidates all cookies.

The login limiter permits eight attempts per direct peer per minute, with bounded
peer storage. It does not trust `X-Forwarded-For`: behind a proxy, clients can share
one bucket. This is a modest local-service safeguard, not distributed attack
protection. It is not an independently audited security design.

See [SECURITY.md](SECURITY.md) before changing network exposure. In particular, a
browser token is not the same thing as an established WebRTC media peer. The gateway
does not provide authoritative per-user media-peer revocation.

## HTTPS and reverse proxies

Native TLS uses Python's server SSL context with a TLS 1.2 minimum and requires both
certificate and key. No certificates are generated or trusted automatically.

For a reverse proxy, bind the Python web server to loopback and set the exact
external origin:

```toml
[server]
host = "127.0.0.1"
port = 8090
public_origin = "https://display.example.com"
```

Conceptual nginx server/location fragment (supply your own valid TLS configuration):

```nginx
location / {
    proxy_pass http://127.0.0.1:8090;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 120s;
    proxy_buffering off;
}
```

Serve the application at the origin root, not an arbitrary subpath. Preserve the
browser's `Origin` header. The example is not an automated deployment or a tested
nginx configuration for your environment. HTTPS proxies the web/signaling/control
path; the browser still needs a route to UDP `8189`. A public DNS name does not
supply TURN, NAT traversal, or a public address for media automatically.

## Tests and screenshots

```bash
python -m unittest discover -s tests -v
python tools/smoke_demo.py
python -m compileall -q app.py host.py settings.py security.py input_protocol.py doctor.py launcher.py
for script in setup.sh start.sh run.sh; do bash -n "$script"; done
```

The standard-library unittest suite includes isolated helpers and real in-process
aiohttp HTTP/WebSocket exchanges. It does not launch Mutter or Docker.

For offline screenshots of the real interface with explicit demo/mock data:

```bash
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python tools/render_preview.py
```

For the optional localhost Demo end-to-end browser workflow:

```bash
python tools/screenshots.py
```

Both scripts accept `--browser /path/to/chromium` and `--output /path/to/images`.
They use a local browser automation process; do not point them at a personal browser
profile. The offline tool performs no browser navigation or network access.
The localhost tool starts its own authenticated demo server with an ephemeral
password and tests login/logout through the browser. It requires an environment
that allows localhost browser navigation; that portion was not runnable in the
packaging environment. It is supplied as a reproducible follow-up check, not a
claimed passed test.

The committed images were generated by **`tools/render_preview.py`**. Never remove
the Demo disclosure to imply hardware testing. Real host screenshots can replace
them after a reproducible real-device capture; remove credentials, addresses, and
personal windows first. See [docs/SCREENSHOTS.md](docs/SCREENSHOTS.md).

### Real-host release checklist

Before calling a release tested on a particular distribution/device, verify the
whole path: new monitor appears → window can be moved to it → live video reaches
client → pointer/buttons/keyboard work → audio monitor plays → source switching
recovers → reconnect works → fullscreen retains Focus → disconnect releases input
→ shutdown removes monitor/container. Repeat on a real phone, test orientation and
native keyboard composition, and verify firewall behavior from a second host.

Test negative paths too: missing plugin, stopped Docker, occupied ports, invalid
config, invalid audio source, denied permissions, no network, registry unreachable,
and interrupted startup. Save actual versions and results instead of inventing a
support matrix. The current report is [docs/TESTING.md](docs/TESTING.md).

## Contribution and publication notes

Keep passwords out of configuration examples, source, logs, screenshots, and bug
reports. Add tests for new configuration fields and input messages. Avoid silent
privilege escalation, automatic firewall edits, deleting unrelated containers, or
claiming support for a desktop you have not tested. Preserve the clean user README;
put implementation details here.

The repository includes a CI workflow, but a workflow file is **not** evidence that
GitHub Actions has run. Run it in the destination repository and perform the
real-host checks before applying a tested-release label.

The original archive had no author/license metadata sufficient to assign a reuse
license. The owner must choose and add an appropriate `LICENSE` after confirming
rights to the supplied code. Do not add an MIT/GPL badge or invented copyright
holder as a documentation shortcut. See [LICENSE-NOTICE.md](LICENSE-NOTICE.md).

## Upstream technical references

The following upstream sources informed interface/configuration checks; they do not
certify this application:

- [Mutter 48 ScreenCast D-Bus API][mutter-sc] and [RemoteDesktop API][mutter-rd].
- [MediaMTX Docker installation][mtx-install], [configuration][mtx-config], and
  [v1.21.0 configuration schema][mtx-schema].
- [MediaMTX reader page][mtx-reader] and [WHEP HTTP routing][mtx-http].
- [aiohttp server lifecycle and cleanup contexts][aiohttp].
- [Debian 13's GStreamer RTSP plugin package][debian-rtsp].
- [Docker port-publishing security and version caveat][docker-ports].
- [NGINX WebSocket proxy requirements][nginx-ws].

[mutter-sc]: https://raw.githubusercontent.com/GNOME/mutter/48.0/data/dbus-interfaces/org.gnome.Mutter.ScreenCast.xml
[mutter-rd]: https://raw.githubusercontent.com/GNOME/mutter/48.0/data/dbus-interfaces/org.gnome.Mutter.RemoteDesktop.xml
[mtx-install]: https://mediamtx.org/docs/kickoff/install
[mtx-config]: https://mediamtx.org/docs/features/configuration
[mtx-schema]: https://raw.githubusercontent.com/bluenviron/mediamtx/v1.21.0/mediamtx.yml
[mtx-http]: https://raw.githubusercontent.com/bluenviron/mediamtx/v1.21.0/internal/servers/webrtc/http_server.go
[mtx-reader]: https://raw.githubusercontent.com/bluenviron/mediamtx/v1.21.0/internal/servers/webrtc/read_index.html
[aiohttp]: https://docs.aiohttp.org/en/stable/web_advanced.html
[debian-rtsp]: https://packages.debian.org/trixie/gstreamer1.0-rtsp

[docker-ports]: https://docs.docker.com/engine/network/port-publishing/
[nginx-ws]: https://nginx.org/en/docs/http/websocket.html
