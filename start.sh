#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
PYTHON="${VSCREEN_PYTHON:-/usr/bin/python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "ERROR: Python 3.11+ is missing ($PYTHON)."
  echo "On Debian/Ubuntu, run: sudo apt update && sudo apt install python3"
  # A diagnostic or explicitly non-installing command must never install Python.
  for arg in "$@"; do
    case "$arg" in
      --doctor|--no-install|--help|-h|--version) exit 2 ;;
    esac
  done
  if [[ -t 0 ]] && command -v apt-get >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then
    read -r -p "Install the distribution's Python package now? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]; then
      sudo apt-get update && sudo apt-get install python3
    else
      exit 2
    fi
  else
    exit 2
  fi
fi
if ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3,11))'; then
  echo "ERROR: Python 3.11+ is required. Use Debian 13's /usr/bin/python3 or set VSCREEN_PYTHON."
  exit 2
fi
for file in launcher.py settings.py doctor.py; do
  [[ -f "$file" ]] || { echo "ERROR: Missing project file: $file. Re-extract the complete release." >&2; exit 2; }
done
exec "$PYTHON" launcher.py "$@"
