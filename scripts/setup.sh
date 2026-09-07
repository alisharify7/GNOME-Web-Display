#!/usr/bin/env bash
# Installs distribution packages only after consent. Does not edit system config.
set -euo pipefail
YES=0
CHECK=0
for arg in "$@"; do
  case "$arg" in
    --yes) YES=1 ;;
    --check) CHECK=1 ;;
    --help|-h) echo "Usage: bash setup.sh [--check | --yes]"; exit 0 ;;
    *) echo "ERROR: Unknown argument: $arg" >&2; exit 2 ;;
  esac
done
if ! command -v apt-get >/dev/null 2>&1 || ! command -v dpkg-query >/dev/null 2>&1; then
  echo "ERROR: Automatic installation supports Debian/Ubuntu (apt) only."
  echo "Install the equivalent packages for your distribution; see docs/DEVELOPMENT.md."
  exit 2
fi
PACKAGES=(python3 python3-gi python3-aiohttp gir1.2-glib-2.0 libglib2.0-bin
  pipewire pipewire-bin pipewire-pulse wireplumber pulseaudio-utils
  gstreamer1.0-tools gstreamer1.0-pipewire gstreamer1.0-pulseaudio
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad
  gstreamer1.0-plugins-ugly gstreamer1.0-rtsp iproute2 ca-certificates)
missing=()
for p in "${PACKAGES[@]}"; do
  status="$(dpkg-query -W -f='${Status}' "$p" 2>/dev/null || true)"
  [[ "$status" == "install ok installed" ]] || missing+=("$p")
done
# Respect existing Docker CE installations; never install docker.io over them.
command -v docker >/dev/null 2>&1 || missing+=(docker.io)
if ((${#missing[@]} == 0)); then
  echo "All distribution packages are installed. Run ./start.sh --doctor for runtime checks."
  exit 0
fi
echo "Missing packages:"
printf '  %s\n' "${missing[@]}"
(( CHECK == 0 )) || exit 1
if (( YES == 0 )); then
  if [[ ! -t 0 ]]; then
    echo "No terminal for confirmation. Run bash setup.sh interactively, or pass --yes explicitly."
    exit 2
  fi
  echo "APT may enable services or replace conflicting audio packages. Review its transaction."
  read -r -p "Install these packages now? [y/N] " answer
  [[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]] || { echo "Installation cancelled; no changes made."; exit 1; }
fi
SUDO=()
if (( EUID != 0 )); then
  command -v sudo >/dev/null 2>&1 || { echo "ERROR: sudo is missing. Ask your administrator to run setup.sh."; exit 2; }
  SUDO=(sudo)
fi
"${SUDO[@]}" apt-get update
OPTIONS=()
(( YES == 0 )) || OPTIONS=(-y)
"${SUDO[@]}" apt-get install "${OPTIONS[@]}" "${missing[@]}"
echo "Packages installed. Return to your normal GNOME terminal and run ./start.sh --doctor."
echo "Docker Engine 28+ is required. Older distro packages need a separate upgrade; see README.md."
