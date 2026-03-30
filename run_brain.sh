#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${AGENTICSWARM_VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"
MIN_DEPS=(pyyaml jsonschema)

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

create_venv_if_missing() {
  if [ -x "$PYTHON_BIN" ]; then
    return
  fi
  echo "Creating local virtual environment at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
}

ensure_pip() {
  "$PYTHON_BIN" -m ensurepip --upgrade >/dev/null 2>&1 || true
}

deps_ready() {
  "$PYTHON_BIN" -c "import yaml, jsonschema" >/dev/null 2>&1
}

install_min_deps() {
  if deps_ready; then
    return
  fi
  echo "Installing local runtime dependencies: ${MIN_DEPS[*]}"
  "$PIP_BIN" install "${MIN_DEPS[@]}"
}

main() {
  require_cmd python3

  if [ ! -f "$ROOT_DIR/scripts/run_audit.py" ]; then
    echo "Unable to locate scripts/run_audit.py under $ROOT_DIR" >&2
    exit 1
  fi

  create_venv_if_missing
  ensure_pip
  install_min_deps

  exec "$PYTHON_BIN" "$ROOT_DIR/scripts/run_audit.py" --repo-root "$ROOT_DIR" "$@"
}

main "$@"
