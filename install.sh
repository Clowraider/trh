#!/bin/sh
set -eu

REPO_SLUG=${TRH_BOOTSTRAP_REPO_SLUG:-Clowraider/trh}
ARCHIVE_URL=${TRH_BOOTSTRAP_ARCHIVE_URL:-https://api.github.com/repos/${REPO_SLUG}/tarball}
INNER_INSTALL_SCRIPT=${TRH_BOOTSTRAP_INNER_INSTALL:-scripts/install.sh}
WORK_DIR=

say() {
  printf '%s\n' "==> $*"
}

fail() {
  printf '%s\n' "Error: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required tool not found: $1"
}

cleanup() {
  status=$?

  if [ -n "${WORK_DIR:-}" ] && [ -d "$WORK_DIR" ]; then
    rm -rf "$WORK_DIR"
  fi

  exit "$status"
}

trap cleanup EXIT HUP INT TERM

require_command curl
require_command tar
require_command mktemp
require_command bash

say "Preparing temporary workspace"
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/trh-install.XXXXXX") || fail "Unable to create a temporary directory"
ARCHIVE_PATH="$WORK_DIR/trh.tar.gz"
EXTRACT_DIR="$WORK_DIR/extract"

mkdir -p "$EXTRACT_DIR" || fail "Unable to create extraction directory"

say "Downloading TRH archive from GitHub"
curl -fsSL "$ARCHIVE_URL" -o "$ARCHIVE_PATH" || fail "Unable to download repository archive from $ARCHIVE_URL"

say "Extracting archive"
tar -xzf "$ARCHIVE_PATH" -C "$EXTRACT_DIR" || fail "Unable to extract repository archive"

PROJECT_DIR=
ENTRY_COUNT=0

for entry in "$EXTRACT_DIR"/*; do
  [ -e "$entry" ] || continue
  ENTRY_COUNT=$((ENTRY_COUNT + 1))
  PROJECT_DIR=$entry
done

[ "$ENTRY_COUNT" -ge 1 ] || fail "No project directory was found in the extracted archive"
[ "$ENTRY_COUNT" -eq 1 ] || fail "Expected exactly one top-level entry in the extracted archive"
[ -d "$PROJECT_DIR" ] || fail "Extracted top-level entry is not a directory: $PROJECT_DIR"

say "Entering project directory: $PROJECT_DIR"
cd "$PROJECT_DIR" || fail "Unable to enter extracted project directory"

[ -f "$INNER_INSTALL_SCRIPT" ] || fail "Expected installer script not found: $INNER_INSTALL_SCRIPT"

say "Running $INNER_INSTALL_SCRIPT"
bash "$INNER_INSTALL_SCRIPT" "$@" || fail "$INNER_INSTALL_SCRIPT exited with an error"

say "Bootstrap installation completed"
