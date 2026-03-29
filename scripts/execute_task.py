from __future__ import annotations

import argparse
from pathlib import Path

try:
    from brain_utils import dump_json_stdout, load_json_file, load_yaml_file, repo_root_from
    from execution_engine import execute_request
except ModuleNotFoundError:
    from scripts.brain_utils import dump_json_stdout, load_json_file, load_yaml_file, repo_root_from
    from scripts.execution_engine import execute_request


def load_request(path: Path) -> dict:
    if path.suffix == ".json":
        return load_json_file(path)
    return load_yaml_file(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute a task through the guarded-autonomy runtime.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--request-file", required=True, help="YAML or JSON execution request file.")
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    payload = load_request((root / args.request_file) if not Path(args.request_file).is_absolute() else Path(args.request_file))
    result = execute_request(str(root), payload)
    dump_json_stdout(result)
    return 0 if result.get("status") in {"success", "awaiting_approval"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
