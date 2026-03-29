#!/usr/bin/env bash
set -euo pipefail

REPO="${AGENTICSWARM_REPO:-james96744/agenticswarm-brain}"
REF="${AGENTICSWARM_REF:-main}"
TARGET="${1:-$PWD}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd curl
require_cmd tar
require_cmd python3

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/agenticswarm-bootstrap.XXXXXX")"
cleanup() {
  rm -rf "$tmpdir"
}
trap cleanup EXIT

archive_url="https://github.com/${REPO}/archive/refs/heads/${REF}.tar.gz"
archive_path="$tmpdir/agenticswarm.tar.gz"

echo "Downloading AgenticSwarm brain scaffold from ${archive_url}"
curl -fsSL "$archive_url" -o "$archive_path"
tar -xzf "$archive_path" -C "$tmpdir"

source_root="$tmpdir/agenticswarm-brain-${REF}"
if [ ! -d "$source_root" ]; then
  echo "Unable to locate extracted scaffold directory: $source_root" >&2
  exit 1
fi

echo "Installing scaffold into ${TARGET}"
python3 "$source_root/install_brain.py" --target "$TARGET"

cat <<'EOF'

Next steps in the target repo:
  1. python3 -m venv .venv
  2. ./.venv/bin/pip install pyyaml jsonschema
  3. ./.venv/bin/python scripts/run_audit.py --repo-root .
EOF
