# Changelog

## 8.0.0 - 2026-09-07

Prepared from the supplied `gnome-web-display-easy-v7.1` archive. This is a packaged
revision, not a claim of real-host certification. See [the validation report](docs/TESTING.md).

### Documentation and presentation

- Replaced the mixed developer/end-user guide with an English consumer README and
  separate `README-dev.md` covering architecture, configuration, APIs, and testing.
- Added six desktop/mobile previews captured from the actual UI with explicit demo
  content, plus reproducible screenshot tools and provenance notes.
- Documented GNOME/Wayland-only scope, security boundaries, network ports, cleanup,
  troubleshooting, migration, and the need for an owner-selected license.

### Setup and configuration

- Added validated TOML configuration and documented environment overrides.
- Added read-only `--doctor` / JSON diagnostics and `setup.sh --check`.
- Missing dependencies now have specific repair messages and consent-based APT
  installation. Noninteractive runs do not silently approve installation.
- Added `--no-install`, explicit `--yes`, `--update-image`, and local-only `--demo`.
- Check ports, GNOME/Wayland/D-Bus, Python modules, PipeWire, GStreamer elements,
  Docker access and Engine version, input configuration, and private password files.
- Require Docker Engine 28+ because this architecture relies on localhost-published
  private media ports; do not silently migrate Docker repositories.

### Runtime and reliability

- Actually mount the bundled MediaMTX configuration read-only; pin the configured
  image to `bluenviron/mediamtx:1.21.0` instead of pulling a floating tag each launch.
- Isolate the startup wrapper, diagnostics, configuration, desktop backend, web
  application, input protocol, and session management into separate modules.
- Track and remove only the container created by this launcher. Reuse cached images;
  supervise child startup/shutdown and clean up on ordinary interruption/failure.
- Add a per-user launch lock, bounded startup probes, persistent private GStreamer
  logs, and an attempted rollback when a live audio-source switch fails.
- Fix PulseAudio source tab parsing; reject unavailable explicitly named sources;
  automatic audio never silently chooses a microphone.

### Browser and access controls

- Responsive toolbar and keyboard layout down to a 320 px viewport; improve Focus
  positioning, fullscreen controls, reconnection, keyboard composition handling,
  accessibility labels, and operation when browser storage is unavailable.
- Track and release held inputs; reject malformed/non-finite values; bound input
  messages, pressed keys, and connection counts.
- Independent expiring sessions, constant-time UTF-8 credential comparison,
  rate-limited sign-in, strict Origin checks, POST sign-out, and restricted WHEP proxy.
- Optional native HTTPS / explicit reverse-proxy origin configuration.
- Distinguish configured FPS/bitrate targets from measured performance; label Demo
  explicitly and never present its sample content as real desktop capture.

### Validation and known limitations

- 73 automated Python tests passed in the packaging environment; HTTP/WebSocket
  tests use real local transports, while host/Docker operations are mocked or not run.
- Offline browser UI assertions and six screenshot captures passed. Real localhost
  browser navigation was blocked by the environment's browser policy, not bypassed.
- Actual Mutter virtual display, GStreamer/MediaMTX end-to-end streaming, audio,
  native phone keyboard, TLS deployment, and Docker network isolation require host
  validation. This is not a cross-desktop or independently audited release.
- No TURN provisioning, hardware encoder backend, user roles, clipboard protocol,
  file transfer, or guaranteed per-peer media revocation is added.

## Supplied 7.1 baseline

The original archive provided GNOME virtual monitor creation, GStreamer publishing,
MediaMTX-based viewing, input forwarding, audio selection, a responsive browser UI,
and shell launch/install scripts. No earlier release history was supplied; none is
invented here.
