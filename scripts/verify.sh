#!/usr/bin/env bash
# Read-only source verification. Package/runtime checks are optional and separate.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd -- "$ROOT"
SOURCE_ONLY=0
case "${1:-}" in
  --source-only) SOURCE_ONLY=1; shift ;;
  --help|-h) echo 'Usage: bash scripts/verify.sh [--source-only]'; exit 0 ;;
esac
(($# == 0)) || { echo 'ERROR: Unexpected verification arguments.' >&2; exit 2; }
for command in sha256sum realpath; do
  command -v "$command" >/dev/null 2>&1 || { echo "ERROR: Install coreutils ($command missing)." >&2; exit 2; }
done
for file in VERSION install.sh start.sh setup.sh scripts/start.sh scripts/setup.sh \
  src/gnome_web_display/__init__.py src/gnome_web_display/paths.py \
  src/gnome_web_display/launcher.py src/gnome_web_display/app.py \
  src/gnome_web_display/doctor.py src/gnome_web_display/settings.py \
  src/gnome_web_display/security.py src/gnome_web_display/input_protocol.py \
  src/gnome_web_display/host.py web/index.html web/login.html web/demo.html \
  config/config.example.toml config/mediamtx.yml MANIFEST.sha256; do
  [[ -f "$file" && ! -L "$file" ]] || { echo "ERROR: Missing/non-regular file: $file" >&2; exit 1; }
done
# Reject absolute/traversing paths and symlinks before handing names to sha256sum.
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^[0-9a-f]{64}\ \ [A-Za-z0-9_./-]+$ ]] || { echo 'ERROR: Invalid manifest entry.' >&2; exit 1; }
  file=${line:66}
  [[ "$file" != /* && "/$file/" != *'/../'* && ! -L "$file" ]] || { echo 'ERROR: Unsafe manifest path.' >&2; exit 1; }
  resolved=$(realpath -e -- "$file") || exit 1
  [[ "$resolved" == "$ROOT/"* ]] || { echo 'ERROR: Manifest path escapes project.' >&2; exit 1; }
done < MANIFEST.sha256
sha256sum --check --quiet --strict MANIFEST.sha256 || { echo 'ERROR: Source checksum mismatch. No setup/start was run.' >&2; exit 1; }
for script in ./*.sh scripts/*.sh; do bash -n "$script"; done
printf 'Source files, SHA-256 manifest and Bash syntax: OK\n'
printf 'Checksums detect file changes; they are not an independent publisher signature.\n'
((SOURCE_ONLY == 0)) || exit 0
result=0
bash setup.sh --check || result=1
bash start.sh --doctor || result=1
exit "$result"
