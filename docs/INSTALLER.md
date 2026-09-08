# Installer reference (v2.0.1)

`install.sh` is intentionally self-contained. It is the only substantial shell
file kept at the root so a raw GitHub URL can bootstrap the complete project.
It uses Bash 5+, Git, GNU coreutils, and Linux. Runtime requirements remain the
GNOME Wayland/Python/PipeWire/GStreamer/Docker requirements in the [README](../README.md).

## Version discovery

The installer obtains remote tags and object IDs with `git ls-remote --tags` over
HTTPS. No GitHub REST token, jq parser, release API pagination or API rate-limit
allowance is needed. Network or repository errors are retried up to three times,
then reported without selecting an invented fallback release.

Only numeric version tags with an optional `v` prefix and optional prerelease /
build suffix are shown. Examples: `v1`, `v1.2`, `v2.0.0`, `2.0.0`, `v3.0.0-rc.1`.
Stable versions are sorted numerically, so `v2.10.0` sorts above `v2.9.0`.

| Selection | Meaning |
| --- | --- |
| `latest` | Highest stable version tag; never `main` or an implicit prerelease |
| `v1`, `v2` (also `1`, `2` in `--version`) | Highest stable tag in that major series |
| `v2.0.0` | Exact tag |
| `2.0.0` | Exact unprefixed tag, falling back to `v2.0.0` when present |
| Menu number | That displayed tag, even if it is a prerelease |

In the interactive version menu a bare number first means a menu index. Use `v2`
to unambiguously choose the v2 series. If no stable tag exists, select a prerelease
explicitly. If no version tags exist at all, the installer stops and asks the owner
to publish one. A missing `v2` does not fall back to `v1` or `main`.

GitHub's Release publication status/"Latest" badge is not consulted. A stable-looking
Git tag is eligible even when no GitHub Release page has been created for it.
If historical tags such as `v8.0.0` exist, `latest` will choose their higher numeric
version; use `--version v2` to stay on the v2 line.

## Action flow

```text
bootstrap checks -> fetch tags -> choose version -> choose action
       -> show trusted-source confirmation for actions executing project code
       -> clone/reuse a verified checkout
          |
          +-- clone:  report path; execute no downloaded project code
          |
          +-- source check (v2 manifest + Bash syntax; legacy Git/syntax fallback)
                  |
                  +-- verify: setup --check + start --doctor; return status
                  +-- setup:  preflight -> setup -> required doctor; stop
                  +-- start:  required doctor -> start --no-install
                  +-- all:    preflight -> setup -> required doctor -> start --no-install
```

An expected dependency failure before setup is printed but does not prevent setup
from repairing it. Python need not be installed to perform the Bash/Git/source
checks. Failure of setup or the final doctor always prevents server launch.
Session/port/unsupported-Docker errors cannot be repaired merely by installing
packages; the user must follow the diagnostic instructions.

`--yes` explicitly approves prompts and is passed to setup/start. It defaults to
`latest` + `all` when neither was specified. It never invents a password or picks
among multiple interfaces. Unattended operation requires a valid private password
file/environment and explicit network configuration, plus any required sudo access.

`--verify-only` still creates a local clone and executes that trusted version's
read-only diagnostic code. It does not install system packages, call sudo from
diagnostics, launch the server or create a media container. `--list` only discovers
tags. `--download-only` does not execute even the downloaded source verifier.

## Terminal handling and shutdown

For `curl ... | bash`, stdin contains the program. All function definitions appear
before `main`; menus use a separate `/dev/tty` descriptor. Setup and launcher
children inherit that terminal as stdin so their interactive checks still work.
Without a controlling terminal, explicit CLI options are required and child stdin
is `/dev/null`; arbitrary piped answers are never treated as consent.

The foreground start uses `exec` to replace the installer with the normal launcher.
Ctrl+C/SIGTERM therefore reach the existing supervisor/cleanup path. No background
service, autostart entry or global shell command is installed.

## Installation safety

Default layout: `$HOME/.local/share/gnome-web-display/versions/<tag>`.
`--install-dir` changes the base, not the per-version directory naming scheme.
Temporary clone directories are created inside that base with private permissions.
The destination is populated with a no-clobber rename only after Git verification.
A competing installation cannot be merged into or overwritten by that rename.

Both the tag object ID (important for annotated tags) and peeled commit ID are
compared with the discovery result. An explicit tag refspec disambiguates a branch
with the same name. Git hooks are disabled for installer Git operations. Git object
checks and a clean tracked/untracked status are required before reusing a checkout.
Ignored private configuration files are left alone.

The installer never resets local changes, pulls into an existing working tree,
replaces another repository, or deletes an installed version on failure. Failed
partial clones are removed; a complete downloaded version is retained when setup
fails, so it can be inspected or repaired. Tag retargeting or a changed checkout
requires investigation or a new install base, not a forced reset.

The bundled manifest is change detection, **not a detached signature**. A malicious
repository can publish a matching manifest. No GPG/Sigstore/signing-key verification
is implemented. Always trust and review the source before running it.

## Compatibility with old layouts

The installer calls root `setup.sh` and `start.sh`; this works with the v1 layout
as well as the v2 thin wrappers. Older releases can carry stale packaging manifests.
When `scripts/verify.sh` is absent, the installer uses pinned Git objects, the clean
checkout and shell syntax checks rather than treating the old manifest as authority.
It does not alter or fix old tagged source, including any old internal version label.

For v2, `scripts/verify.sh --source-only` checks the distributed file manifest and
syntax without requiring Python. Intentional source edits invalidate that manifest:
review the changes and regenerate it with `python tools/manifest.py` before publishing.
Do not regenerate it merely to silence an unexpected integrity failure.

## Useful commands

```bash
bash install.sh --help
bash install.sh --list
bash install.sh --version v2 --action verify
bash install.sh --version v2.0.0 --action clone
bash install.sh --version v2 --action setup
bash install.sh --version v2 --action start
bash install.sh --version v2 --action all
bash install.sh --version v2 --action start --config /absolute/path/config.toml
bash install.sh --version v2 --action start --demo
```

For a trusted fork, pass `--repo OWNER/REPO` and use a separate `--install-dir` to
avoid colliding with this repository's existing versions. That changes which code
is fetched and executed; never use a repository supplied by an untrusted party.

See [RELEASING.md](RELEASING.md) before announcing the curl command or a new version.
