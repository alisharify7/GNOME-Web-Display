#!/usr/bin/env bash
# Standalone bootstrap: keep this file self-contained for curl | bash.
# All definitions precede main so prompts never consume the downloaded program.
set -euo pipefail

info() { printf '%s\n' "$*" >&2; }
fail() { info "ERROR: $*"; exit 1; }
usage() {
  cat <<'EOF'
GNOME Web Display installer v2
Usage: bash install.sh [options]

Without options: choose a published tag and an action in a terminal menu.
  --version TAG      Exact tag (v2.0.0), major series (v1/v2), or latest
  --list             List remote version tags; do not clone/install/run anything
  --action ACTION    all | verify | setup | start | clone
  --verify-only      Same as --action verify (clone + read-only host checks)
  --no-start         Same as --action setup (verify, setup, recheck; no server)
  --download-only    Same as --action clone (no downloaded code is executed)
  --install-dir DIR  Installation base (default: ~/.local/share/gnome-web-display)
  --repo OWNER/REPO  A trusted GitHub fork (default: alisharify7/GNOME-Web-Display)
  --config FILE      Pass an existing TOML configuration to doctor and start
  --demo             Use local-only preview diagnostics/start; no real capture
  --yes             Explicitly approve prompts, including APT/service changes;
                    defaults to latest + all when no version/action is supplied
  --help            Show this help

latest = numerically highest stable version tag, NOT main or GitHub's Latest flag.
v2 = highest stable 2.x tag; prereleases must be selected by their exact tag.
Use a normal user inside GNOME Wayland, never sudo for the entire installer.
Versions are installed separately under INSTALL_DIR/versions/<tag>.
Existing modified checkouts are never overwritten, reset, or deleted.
Noninteractive runs need --version and --action (or explicit --yes).
EOF
}

init_options() {
  REPO='alisharify7/GNOME-Web-Display'
  INSTALL_BASE="${HOME:?HOME must be set}/.local/share/gnome-web-display"
  REQUESTED='' ACTION='' YES=0 LIST=0 HAS_TTY=0 STAGING='' DEST=''
  CONFIG='' DEMO=0 SELECTED='' LATEST='' REMOTE_URL=''
  declare -ga TAGS=() STABLE_TAGS=() START_ARGS=()
  declare -gA TAG_OIDS=() TAG_COMMITS=()
}

parse_options() {
  while (($#)); do
    case "$1" in
      --version|--action|--install-dir|--repo|--config)
        (($# >= 2)) && [[ -n "$2" ]] || fail "$1 requires a value."
        case "$1" in
          --version) REQUESTED=$2 ;;
          --action) ACTION=$2 ;;
          --install-dir) INSTALL_BASE=$2 ;;
          --repo) REPO=$2 ;;
          --config) CONFIG=$2 ;;
        esac
        shift 2 ;;
      --list) LIST=1; shift ;;
      --yes) YES=1; shift ;;
      --demo) DEMO=1; shift ;;
      --verify-only) ACTION=verify; shift ;;
      --no-start) ACTION=setup; shift ;;
      --download-only) ACTION=clone; shift ;;
      --help|-h) usage; exit 0 ;;
      *) fail "Unknown argument: $1. Use --help." ;;
    esac
  done
  [[ "$REPO" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || fail 'Use --repo OWNER/REPO, not a URL.'
  case "$ACTION" in ''|all|verify|setup|start|clone) ;; *) fail "Unknown action: $ACTION" ;; esac
  [[ -n "$INSTALL_BASE" && "$INSTALL_BASE" != / ]] || fail 'Choose a non-root installation directory.'
  REMOTE_URL="https://github.com/$REPO.git"
  if [[ -n "$CONFIG" ]]; then
    [[ -f "$CONFIG" ]] || fail "Configuration file not found: $CONFIG"
    CONFIG="$(cd -- "$(dirname -- "$CONFIG")" && pwd)/$(basename -- "$CONFIG")"
    START_ARGS+=(--config "$CONFIG")
  fi
  ((DEMO == 0)) || START_ARGS+=(--demo)
}

open_terminal() {
  # A pipe contains the installer, not answers. Children also receive this TTY.
  if { exec 3<>/dev/tty; } 2>/dev/null; then
    HAS_TTY=1
  elif [[ -t 0 ]]; then
    exec 3<&0
    HAS_TTY=1
  fi
}

ask() {
  local prompt=$1
  ((HAS_TTY)) || fail 'No interactive terminal. Use --version and --action; use --yes only to explicitly approve changes.'
  printf '%s' "$prompt" >&2
  IFS= read -r REPLY <&3 || fail 'Input closed; cancelled.'
}

confirm() {
  ((YES)) && return 0
  ask "$1 [y/N] "
  [[ "$REPLY" =~ ^[Yy]([Ee][Ss])?$ ]]
}

bootstrap() {
  [[ "$(uname -s)" == Linux ]] || fail 'This installer targets Linux; the server needs GNOME Wayland.'
  local utility
  for utility in sort mktemp mkdir mv rm; do
    command -v "$utility" >/dev/null 2>&1 || fail "Missing bootstrap command: $utility"
  done
  sort -V </dev/null >/dev/null 2>&1 || fail 'GNU/coreutils sort with -V is required.'
  if ! command -v git >/dev/null 2>&1; then
    if ((LIST)) || [[ "$ACTION" == verify || "$ACTION" == clone || "$ACTION" == start ]]; then
      fail 'Git is missing. Install git and ca-certificates, then retry. No system changes made.'
    fi
    command -v apt-get >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1 || fail 'Install git and ca-certificates using your package manager, then retry.'
    confirm 'Git is missing. Install git and ca-certificates with APT?' || fail 'Cancelled; Git was not installed.'
    local apt_args=()
    ((YES == 0)) || apt_args=(-y)
    if ((HAS_TTY)); then
      sudo apt-get update <&3
      sudo apt-get install "${apt_args[@]}" git ca-certificates <&3
    else
      sudo -n apt-get update </dev/null
      sudo -n apt-get install "${apt_args[@]}" git ca-certificates </dev/null
    fi
  fi
}

remote_git() {
  # No Git credential prompt may read the pipe containing this program.
  GIT_TERMINAL_PROMPT=0 git -c core.hooksPath=/dev/null \
    -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=30 "$@"
}

fetch_versions() {
  local output='' attempt sha ref tag ordered
  info "Fetching version tags from $REMOTE_URL ..."
  for attempt in 1 2 3; do
    if output=$(remote_git ls-remote --tags "$REMOTE_URL"); then break; fi
    ((attempt < 3)) || fail 'Cannot fetch version tags. Check DNS, HTTPS access and the repository name. Nothing was cloned.'
    info "Retrying tag discovery ($attempt/3)..."
    sleep "$attempt"
  done
  while IFS=$'\t' read -r sha ref; do
    [[ "$sha" =~ ^([0-9a-f]{40}|[0-9a-f]{64})$ ]] || continue
    [[ "$ref" == refs/tags/* ]] || continue
    tag=${ref#refs/tags/}
    if [[ "$tag" == *'^{}' ]]; then
      tag=${tag%'^{}'}
      [[ "$tag" =~ ^v?[0-9]+(\.[0-9]+){0,2}(-[A-Za-z0-9][A-Za-z0-9.-]*)?(\+[A-Za-z0-9][A-Za-z0-9.-]*)?$ ]] || continue
      TAG_COMMITS["$tag"]=$sha
    else
      [[ "$tag" =~ ^v?[0-9]+(\.[0-9]+){0,2}(-[A-Za-z0-9][A-Za-z0-9.-]*)?(\+[A-Za-z0-9][A-Za-z0-9.-]*)?$ ]] || continue
      TAG_OIDS["$tag"]=$sha
    fi
  done <<< "$output"
  ((${#TAG_OIDS[@]})) || fail 'No version tags are published. The owner must push a tag such as v2.0.0; main is not a release.'
  ordered=$(for tag in "${!TAG_OIDS[@]}"; do printf '%s\t%s\n' "${tag#v}" "$tag"; done | LC_ALL=C sort -t $'\t' -k1,1Vr -k2,2r)
  while IFS=$'\t' read -r _ tag; do
    TAGS+=("$tag")
    [[ -n "${TAG_COMMITS[$tag]:-}" ]] || TAG_COMMITS["$tag"]=${TAG_OIDS[$tag]}
    if [[ "$tag" =~ ^v?[0-9]+(\.[0-9]+){0,2}(\+[A-Za-z0-9][A-Za-z0-9.-]*)?$ ]]; then
      STABLE_TAGS+=("$tag")
    fi
  done <<< "$ordered"
  LATEST=${STABLE_TAGS[0]:-}
}

resolve_version() {
  local request=$1 tag major normal
  SELECTED=''
  if [[ "$request" == latest ]]; then
    SELECTED=$LATEST
  elif [[ "$request" =~ ^v?[0-9]+$ ]]; then
    major=${request#v}
    for tag in "${STABLE_TAGS[@]}"; do
      normal=${tag#v}; normal=${normal%%+*}
      if [[ "${normal%%.*}" == "$major" ]]; then SELECTED=$tag; break; fi
    done
  elif [[ "$request" =~ ^v?[0-9]+(\.[0-9]+){1,2}(-[A-Za-z0-9][A-Za-z0-9.-]*)?(\+[A-Za-z0-9][A-Za-z0-9.-]*)?$ ]]; then
    if [[ -n "${TAG_OIDS[$request]:-}" ]]; then
      SELECTED=$request
    elif [[ "$request" != v* && -n "${TAG_OIDS[v$request]:-}" ]]; then
      SELECTED="v$request"
    fi
  fi
  [[ -n "$SELECTED" ]]
}

show_versions() {
  local tag
  printf 'Repository: %s\n' "$REPO"
  printf 'latest: %s\n' "${LATEST:-unavailable (only prereleases)}"
  for tag in "${TAGS[@]}"; do printf '  %-24s %s\n' "$tag" "${TAG_COMMITS[$tag]}"; done
}

select_version() {
  local i tag
  if [[ -n "$REQUESTED" ]]; then
    resolve_version "$REQUESTED" || fail "Version '$REQUESTED' is not published. Use --list; v1/v2 select existing stable tags only."
    return
  fi
  if ((YES)); then
    resolve_version latest || fail 'No stable version exists; specify an exact prerelease tag.'
    return
  fi
  info ''
  info 'Choose a release (a number, exact tag, major series such as v1/v2, or latest):'
  for i in "${!TAGS[@]}"; do
    tag=${TAGS[$i]}
    printf '  %2d) %s%s\n' "$((i+1))" "$tag" "$([[ "$tag" == "$LATEST" ]] && printf ' [latest stable]' || true)" >&2
  done
  info '   0) Cancel'
  while :; do
    ask 'Select version [latest]: '
    [[ "$REPLY" != 0 && "$REPLY" != q ]] || exit 0
    if [[ "$REPLY" =~ ^[0-9]{1,5}$ ]] && ((10#$REPLY >= 1 && 10#$REPLY <= ${#TAGS[@]})); then
      SELECTED=${TAGS[$((10#$REPLY-1))]}; return
    fi
    resolve_version "${REPLY:-latest}" && return
    info 'That version is not available. Select a listed tag, v1/v2 series, or latest.'
  done
}

select_action() {
  [[ -z "$ACTION" ]] || return 0
  if ((YES)); then ACTION=all; return; fi
  info ''
  info '  1) Verify -> setup -> recheck -> start (recommended)'
  info '  2) Verify only (clone + read-only checks; no packages or server)'
  info '  3) Verify -> setup -> recheck (do not start)'
  info '  4) Verify -> start (never install packages)'
  info '  5) Clone only (do not execute downloaded code)'
  info '  0) Cancel'
  while :; do
    ask 'Select action [1]: '
    case "${REPLY:-1}" in
      1) ACTION=all; return ;; 2) ACTION=verify; return ;;
      3) ACTION=setup; return ;; 4) ACTION=start; return ;;
      5) ACTION=clone; return ;; 0|q) exit 0 ;;
      *) info 'Choose 0 through 5.' ;;
    esac
  done
}

cleanup() {
  # Only remove our own temporary directory, never an installed version.
  [[ -z "$STAGING" || ! -d "$STAGING" ]] || rm -rf -- "$STAGING"
}

validate_checkout() {
  local dir=$1 top origin oid commit changes script
  [[ -d "$dir/.git" && ! -L "$dir" ]] || fail "Not a regular installer checkout: $dir"
  top=$(remote_git -C "$dir" rev-parse --show-toplevel)
  [[ "$top" == "$dir" ]] || fail 'Refusing a nested or redirected checkout.'
  # remote get-url applies user's insteadOf rewrites; use the stored URL instead.
  origin=$(remote_git -C "$dir" config --get remote.origin.url)
  [[ "$origin" == "$REMOTE_URL" ]] || fail 'Existing checkout belongs to another repository; choose another --install-dir.'
  oid=$(remote_git -C "$dir" rev-parse --verify "refs/tags/$SELECTED") || fail 'Selected tag is missing from the checkout.'
  commit=$(remote_git -C "$dir" rev-parse --verify "refs/tags/$SELECTED^{commit}") || fail 'Selected tag does not name a commit.'
  [[ "$oid" == "${TAG_OIDS[$SELECTED]}" && "$commit" == "${TAG_COMMITS[$SELECTED]}" ]] || fail 'The tag changed after discovery, or this installation is from a different tag object. Refusing to execute it.'
  [[ "$(remote_git -C "$dir" rev-parse HEAD)" == "$commit" ]] || fail 'Existing checkout is at another commit; it will not be reset.'
  changes=$(remote_git -C "$dir" status --porcelain --untracked-files=normal)
  [[ -z "$changes" ]] || fail "Existing checkout has local changes/untracked files: $dir. Preserve them and choose a new --install-dir; no files were overwritten."
  remote_git -C "$dir" fsck --no-reflogs --no-dangling >/dev/null || fail 'Git object verification failed.'
  for script in start.sh setup.sh; do
    [[ -f "$dir/$script" && ! -L "$dir/$script" ]] || fail "Release is missing a regular $script file."
    bash -n "$dir/$script" || fail "Shell syntax failed: $script"
  done
  info "Verified tag + commit: $SELECTED -> $commit"
  info 'This checks source consistency, not an independent publisher signature.'
}

clone_release() {
  umask 077
  mkdir -p -- "$INSTALL_BASE/versions"
  INSTALL_BASE="$(cd -- "$INSTALL_BASE" && pwd -P)"
  DEST="$INSTALL_BASE/versions/$SELECTED"
  if [[ -e "$DEST" || -L "$DEST" ]]; then
    info "Checking existing installation: $DEST"
    validate_checkout "$DEST"
    return
  fi
  STAGING=$(mktemp -d "$INSTALL_BASE/.gwd-install.XXXXXXXX")
  info "Cloning $SELECTED into $DEST ..."
  remote_git clone --no-checkout --depth 1 --single-branch --branch "$SELECTED" -- "$REMOTE_URL" "$STAGING/repository" || fail 'Clone failed; no installed version was replaced.'
  # Explicit refspec also disambiguates a branch sharing the tag's name.
  remote_git -C "$STAGING/repository" fetch --depth 1 origin "refs/tags/$SELECTED:refs/tags/$SELECTED" || fail 'Cannot fetch the selected tag.'
  local oid commit
  oid=$(remote_git -C "$STAGING/repository" rev-parse "refs/tags/$SELECTED")
  commit=$(remote_git -C "$STAGING/repository" rev-parse "refs/tags/$SELECTED^{commit}")
  [[ "$oid" == "${TAG_OIDS[$SELECTED]}" && "$commit" == "${TAG_COMMITS[$SELECTED]}" ]] || fail 'Remote tag changed during installation. Retry after reviewing the repository; nothing was executed.'
  remote_git -C "$STAGING/repository" -c advice.detachedHead=false checkout --detach "$commit" --
  validate_checkout "$STAGING/repository"
  # GNU mv -T -n never merges into or overwrites an existing destination.
  mv -T -n -- "$STAGING/repository" "$DEST"
  [[ ! -d "$STAGING/repository" ]] || fail 'Another installer created the destination. Retry; its files were not overwritten.'
  cleanup
  STAGING=''
}

run_script() {
  local script=$1; shift
  if ((HAS_TTY)); then
    (cd -- "$DEST" && exec bash "$script" "$@" <&3)
  else
    (cd -- "$DEST" && exec bash "$script" "$@" </dev/null)
  fi
}

source_checks() {
  if [[ -f "$DEST/scripts/verify.sh" && ! -L "$DEST/scripts/verify.sh" ]]; then
    run_script scripts/verify.sh --source-only
  else
    # Old releases contain stale packaging manifests; Git remains authoritative.
    info 'Legacy layout: using pinned Git objects + clean checkout + shell syntax checks.'
    info 'Legacy MANIFEST.sha256 is not used as publisher authentication.'
  fi
}

preflight() {
  local failed=0
  info $'\n--- Dependency package audit (read-only) ---'
  run_script setup.sh --check || failed=1
  info $'\n--- Host/runtime diagnostics (read-only) ---'
  run_script start.sh --doctor "${START_ARGS[@]}" || failed=1
  return "$failed"
}

execute_action() {
  info "Installed source: $DEST"
  if [[ "$ACTION" == clone ]]; then
    info 'Clone only: no downloaded code, dependency installer or server was executed.'
    printf 'Next: cd %q && bash setup.sh && bash start.sh\n' "$DEST"
    return
  fi
  source_checks || fail 'Source verification failed. Setup and server were not run.'
  if [[ "$ACTION" == verify ]]; then
    preflight
    return
  fi
  if [[ "$ACTION" == all || "$ACTION" == setup ]]; then
    # Missing packages/Python before setup are findings, not a dead end.
    if ! preflight; then
      info 'Preflight found issues. Setup can repair packages, not desktop/session/port problems.'
    fi
    info $'\n--- Running setup.sh ---'
    local setup_args=()
    ((YES == 0)) || setup_args=(--yes)
    run_script setup.sh "${setup_args[@]}" || fail "Setup did not finish successfully. Server was not started. Source remains at $DEST"
  fi
  info $'\n--- Required runtime check before starting ---'
  run_script start.sh --doctor "${START_ARGS[@]}" || fail "Runtime checks still fail. No server was started. Fix the reported issues, then run: bash $DEST/start.sh --doctor"
  if [[ "$ACTION" == setup ]]; then
    info 'Setup and runtime verification finished; server was not started.'
    return
  fi
  info 'Starting in the foreground. Keep this terminal open; Ctrl+C stops the server.'
  local launch_args=(--no-install)
  ((YES == 0)) || launch_args+=(--yes)
  cd -- "$DEST"
  # Replace the installer so terminal signals reach the normal cleanup launcher.
  if ((HAS_TTY)); then
    exec bash ./start.sh "${launch_args[@]}" "${START_ARGS[@]}" <&3
  else
    exec bash ./start.sh "${launch_args[@]}" "${START_ARGS[@]}" </dev/null
  fi
}

main() {
  ((BASH_VERSINFO[0] >= 5)) || fail 'Bash 5+ is required. Run with bash, not sh.'
  init_options
  parse_options "$@"
  open_terminal
  if ((LIST == 0 && EUID == 0)); then
    fail 'Do not run this installer with sudo/as root. Use your logged-in desktop user; setup may request sudo separately.'
  fi
  if ((LIST == 0 && HAS_TTY == 0 && YES == 0)); then
    [[ -n "$REQUESTED" && -n "$ACTION" ]] || fail 'No terminal: provide --version and --action, or use --yes explicitly.'
  fi
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  bootstrap
  fetch_versions
  if ((LIST)); then show_versions; return; fi
  select_version
  select_action
  info "Selected: $SELECTED | action: $ACTION | repository: $REPO"
  if [[ "$ACTION" != clone ]]; then
    info 'This action executes scripts from the selected repository as your user.'
    if ((HAS_TTY || YES)); then
      confirm 'Continue with this trusted source?' || fail 'Cancelled; nothing cloned or executed.'
    else
      # Explicit noninteractive verify/start is allowed, but setup needs approval.
      [[ "$ACTION" == verify || "$ACTION" == start ]] || fail 'Noninteractive package installation requires explicit --yes.'
    fi
  fi
  clone_release
  execute_action
}

if [[ -z "${BASH_SOURCE[0]:-}" || "${BASH_SOURCE[0]:-}" == "$0" ]]; then
  main "$@"
fi
