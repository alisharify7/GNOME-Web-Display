# v2.0.0 validation report

Prepared on 2026-09-07 from the supplied GNOME-Web-Display source archive. These
results describe this build environment, not a certified GNOME host or a published
GitHub Actions run. The original packaging report and results are retained in
[history](history/packaging-validation.md).

## Completed checks

| Check | Result and scope |
| --- | --- |
| Python application/API suite | Original 73 tests pass after the package/path refactor |
| Installer integration suite | 40 tests pass using real local Git repositories and isolated HOME directories; setup/start fixtures do not install system packages |
| Layout/version suite | 7 tests pass, including entry points launched from another working directory |
| Total automated tests | 120 tests passed under Python 3.13 in this build environment |
| Shell parsing | Root and scripts/ Bash entry points parse with `bash -n` |
| Direct demo startup | Real launcher, HTTP login/session/logout, health and SIGTERM cleanup pass without GNOME/Docker |
| Offline browser UI | Real relocated templates render in Chromium; Focus/fullscreen/keyboard and responsive widths pass; six demo images regenerated |
| Real-project installer smoke | Local annotated Git tag -> clone -> source verification -> actual demo HTTP login/versioned health -> SIGTERM cleanup pass; altered source is rejected |
| Source integrity | Release manifest is regenerated and checked; source-only verification does not need Python or install packages |

Raw test output is in [test-results.txt](test-results.txt). Installer coverage
includes numeric tag sorting, annotated tags, explicit prereleases, v1/v2 aliases,
missing versions, empty tag lists, noninteractive consent, staged clone cleanup,
changing tags during a clone, branch/tag name collisions, dirty/symlink/untracked
checkout rejection, config preservation, failed setup, failed final diagnostics,
foreground exit codes, and a `cat install.sh | bash` pseudo-terminal flow with
actual menu and child-script prompts. Root test processes drop privileges for
install scenarios; the root-refusal test itself runs only in a root test environment.

Git transport tests use a local fixture remote through a test-local `insteadOf`
configuration. They test actual tag discovery/fetch/clone logic without claiming a
successful public GitHub connection. Application setup/start fixture scripts record
calls; they never run APT, Docker or a real desktop capture.

## Environment limitations / not passed as live tests

The public GitHub clone attempt could not resolve `github.com` in the container.
A public curl installation must therefore be checked after the owner pushes the
installer and tag. No public release, commit or tag was created by this build.

The optional browser-navigation harness `tools/screenshots.py` reached a browser
policy error (`net::ERR_BLOCKED_BY_ADMINISTRATOR`) when opening localhost. The policy
was not bypassed. Offline `page.set_content` checks passed, and separate Python HTTP
smoke tests passed; a live browser-driven login session was not validated here.

No GNOME Wayland/Mutter monitor was created. Physical phones, real input/audio,
Docker-backed MediaMTX delivery, APT package installation, administrator prompts
against a real system, TLS on client devices, LAN isolation and hardware latency
were not validated. Do not treat successful portable tests as a claim of support
for a particular distribution/device or as a security/performance audit.

An inherited aiohttp warning about returning an HTTP exception is present in the
original application tests; the installer/layout work does not claim to change the
application's redirect/middleware behavior.

## Repeat the portable checks

From the repository root, with the development dependencies available:

```bash
python -m unittest discover -s tests -v
python tools/smoke_demo.py
python tools/smoke_installer.py
python tools/render_preview.py
python -m compileall -q src tests tools
for script in install.sh start.sh setup.sh run.sh scripts/*.sh; do bash -n "$script"; done
python tools/manifest.py --check
bash scripts/verify.sh --source-only
```

After intentionally changing source, documentation or committed preview images,
review the changes and run `python tools/manifest.py` before checking the manifest.
CI runs source-integrity checks from a fresh checkout, before generating previews
in its separate UI job. A workflow definition is not evidence that CI ran remotely.

## Real-host release checklist

Record distribution, GNOME/Mutter, PipeWire, GStreamer, Docker Engine, image,
GPU/driver, client OS/browser and network versions with your results.

- [ ] Publish the reviewed installer and tag, then verify public curl, version list,
  v1/v2 selection, a fresh install and reuse of a clean installation.
- [ ] Start from a normal GNOME Wayland terminal; check missing dependencies,
  inaccessible/stopped Docker, unsupported Docker versions and occupied ports.
- [ ] Arrange the new monitor in GNOME Settings -> Displays and move harmless
  content onto it; confirm that it is the intended monitor being shared.
- [ ] Test a desktop browser and physical phone: pointer edges, dragging, modifiers,
  keyboard composition, Focus/fullscreen, orientation changes and held-key cleanup.
- [ ] Test system-output audio, explicit sources, video-only, source changes,
  autoplay/unmute and reconnect behavior with actual devices.
- [ ] Test authentication/rate limiting/expiry/sign-out, trusted HTTPS and Origin
  checks; ensure private media ports are not reachable from another LAN device.
- [ ] Test Ctrl+C, SIGTERM, failed/interrupted startup and cleanup of only this
  launcher's container/monitor/publisher. Keep sensitive data out of reports.
