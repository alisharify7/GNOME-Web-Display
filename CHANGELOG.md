# Changelog

## 2.0.0 - 2026-09-07 (prepared release; publication is separate)

### Version-selecting installer

- Add a standalone `install.sh` usable through a raw GitHub `curl | bash` URL.
- Discover Git tags without a GitHub API token, jq, or API pagination/rate limits.
- Support exact tags, stable major-series aliases (`v1` / `v2`) and `latest`.
- Add menu actions for the full workflow, verify-only, setup-only, start-only and
  clone-only. Reattach child prompts to the controlling terminal.
- Verify the remote tag object and commit, fetched Git objects and clean checkout;
  use staged, no-clobber installs in separate per-tag directories.
- Audit packages and runtime before setup; do not let expected missing packages
  prevent repair. Require successful post-setup diagnostics before starting.
- Preserve existing installs and private config; refuse dirty/mismatched checkouts.
- Never silently install as root, choose a prerelease, run main as latest, install
  a system service, or force-reset a user checkout.

### Organized source layout

- Move Python to `src/gnome_web_display/`, frontend templates to `web/`, shipped
  configuration to `config/`, and launcher/setup implementation to `scripts/`.
- Retain root `start.sh`, `setup.sh` and `run.sh` as thin compatibility entry points.
- Read the runtime version from `VERSION` instead of a separate hardcoded value.
- Keep private root `config.toml` and the existing `VSCREEN_*` overrides compatible.
- Update media mount paths, module subprocesses, tests, screenshot tools and CI.

### Documentation and validation

- Add installer/developer/publishing guides, v2 release notes and a reproducible
  manifest tool; refresh UI previews from the relocated real templates.
- Add offline integration coverage using real Git repositories, annotated tags,
  tag/branch collisions and a pseudo-terminal pipeline.
- Retain the supplied LICENSE unchanged; correct the contradictory older notice.
- Preserve historical test evidence separately. Current results and untested
  live-host scope are in [docs/TESTING.md](docs/TESTING.md).

The earlier source snapshot used internal labels 8.0.0/v7.1. This public release
line follows the owner's requested v1 -> v2 naming; old published tags are not
retagged by this change.

## Historical packaging snapshot (internally labeled 8.0.0)

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
