from __future__ import annotations

from pathlib import Path
import json
import sys


IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".next",
    ".turbo",
}

IGNORED_PREFIXES = (
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
)


def repo_root_from(value: str | None = None) -> Path:
    if value:
        return Path(value).resolve()
    return Path(__file__).resolve().parents[1]


def require_yaml():
    try:
        import yaml  # type: ignore
    except ImportError:  # pragma: no cover - dependency gate
        print("PyYAML is required. Install with `pip install pyyaml`.", file=sys.stderr)
        raise SystemExit(2)
    return yaml


def load_yaml_file(path: Path):
    yaml = require_yaml()
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def dump_yaml_file(path: Path, data) -> None:
    yaml = require_yaml()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=False)


def load_json_file(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json_stdout(data) -> None:
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")


def safe_relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def iter_repo_files(root: Path):
    for current_root, dirnames, filenames in __import__("os").walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in IGNORED_DIRS and not any(name.startswith(prefix) for prefix in IGNORED_PREFIXES)
        ]
        current_path = Path(current_root)
        for filename in filenames:
            yield current_path / filename
