# Publishing v2.0.0

This source package prepares a release. It does not push commits, tags or GitHub
Releases. The curl command cannot serve this installer until `install.sh` is on
GitHub, and `v2` cannot be selected until an eligible v2 tag is pushed.

## Apply the organized tree

Use this complete source tree, including deletions of the old root Python/HTML/
configuration files. Do not merely copy `src/` alongside stale root implementations.
When applying the supplied patch to a checkout matching the input archive, run
`git apply --check` first and resolve any differences without forcing the patch.
Keep private configuration and passwords out of commits.

## Validate before tagging

From the repository root, in the development environment:

```bash
python tools/manifest.py
python -m unittest discover -s tests -v
python tools/smoke_demo.py
python tools/smoke_installer.py
python tools/render_preview.py
python -m compileall -q src tests tools
for script in install.sh start.sh setup.sh run.sh scripts/*.sh; do bash -n "$script"; done
python tools/manifest.py
python tools/manifest.py --check
bash scripts/verify.sh --source-only
bash start.sh --version
```

`VERSION` must be `2.0.0`, and `start.sh --version` must agree. Update documentation
and validation evidence before the final manifest generation. Do not modify a
manifest-covered file after generating the manifest without regenerating it.
Review `git status --short` and ensure there are no secrets or unintended artifacts.
Automated/demo results are not a substitute for [real-host validation](TESTING.md).

## Publish the commit and tag

Review the actual default branch/remotes in your checkout first. For this project's
`main`/`origin` convention, the commands are:

```bash
git add -A
git commit -m "Release v2.0.0: interactive installer and organized source layout"
git push origin main
git tag -a v2.0.0 -m "GNOME Web Display v2.0.0"
git push origin v2.0.0
```

Do not force-move existing v1 or v2 tags. If `v2.0.0` already exists, choose a new
version and update VERSION/docs instead. Create the GitHub Release from the tag and
use [releases/v2.0.0.md](releases/v2.0.0.md) for its description.

## Confirm public installation paths

Once the commit and tag are visible on GitHub, from a normal desktop terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/alisharify7/GNOME-Web-Display/main/install.sh -o /tmp/gwd-install.sh
bash /tmp/gwd-install.sh --list
bash /tmp/gwd-install.sh --version v2.0.0 --verify-only
```

The fixed bootstrap URL is:

```text
https://raw.githubusercontent.com/alisharify7/GNOME-Web-Display/v2.0.0/install.sh
```

Verify the list contains the intended tag and commit, then test the complete
interactive flow on a real GNOME Wayland host. Preserve older release tags so the
menu can still offer older versions. `latest` follows numeric stable tags, not the
GitHub Release page's manually selected Latest badge.
