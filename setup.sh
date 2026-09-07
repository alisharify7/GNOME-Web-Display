#!/usr/bin/env bash
# Stable entry point; implementation lives in scripts/.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$ROOT/scripts/setup.sh" "$@"
