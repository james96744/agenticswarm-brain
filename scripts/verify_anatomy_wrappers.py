from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

try:
    from brain_utils import dump_json_stdout, repo_root_from
except ModuleNotFoundError:
    from scripts.brain_utils import dump_json_stdout, repo_root_from


def build_safe_request_file() -> str:
    payload = {
        "task_id": "anatomy-wrapper-safe-demo",
        "task_family": "boilerplate_code",
        "description": "Safe anatomy wrapper verification run",
        "risk_level": "low",
        "selected_executor_id": "python-workflow-runner",
        "selected_backend_ids": ["cli-rg"],
        "inputs": {
            "command": ["python3", "-c", "print('anatomy wrapper ok')"],
            "backend_requests": [
                {
                    "backend_id": "cli-rg",
                    "action": "raw_command",
                    "args": ["--files"],
                }
            ],
        },
    }
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", prefix="anatomy-wrapper-", delete=False, encoding="utf-8")
    with handle:
        json.dump(payload, handle)
    return handle.name


def run_command(command: list[str], cwd: Path) -> dict:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    summary = stdout.splitlines()[0] if stdout else (stderr.splitlines()[0] if stderr else "")
    return {
        "command": command,
        "returncode": completed.returncode,
        "status": "passed" if completed.returncode == 0 else "failed",
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Exercise every anatomy wrapper action through the stable registry.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--request-file", default=None, help="Optional execution request file for neurons/brainstem execute actions.")
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    request_file = args.request_file or build_safe_request_file()

    matrix = [
        ("cerebrum", "audit", ["--repo-root", str(root), "--dry-run", "--no-autostart"]),
        ("cerebrum", "discover", ["--repo-root", str(root), "--dry-run"]),
        ("cerebrum", "plan", ["--repo-root", str(root), "--dry-run"]),
        ("cerebellum", "validate", ["--repo-root", str(root)]),
        ("cerebellum", "simulate", ["--repo-root", str(root), "--dry-run"]),
        ("cerebellum", "prune", ["--repo-root", str(root), "--dry-run"]),
        ("cerebellum", "distill", ["--repo-root", str(root), "--dry-run"]),
        ("limbic_system", "reconcile", ["--repo-root", str(root), "--dry-run"]),
        ("neurons", "execute", ["--repo-root", str(root), "--request-file", request_file]),
        ("dendrites", "map", ["--repo-root", str(root), "--dry-run"]),
        ("dendrites", "refresh", ["--repo-root", str(root), "--dry-run"]),
        ("brainstem", "execute", ["--repo-root", str(root), "--request-file", request_file]),
        ("brainstem", "status", ["--repo-root", str(root)]),
    ]

    results = []
    success = True
    for anatomy_key, action, extra_args in matrix:
        command = [sys.executable, str(root / "scripts" / f"{anatomy_key}.py"), action, *extra_args]
        result = run_command(command, root)
        result["anatomy_key"] = anatomy_key
        result["action"] = action
        results.append(result)
        success = success and result["returncode"] == 0

    dump_json_stdout(
        {
            "verified": success,
            "request_file": request_file,
            "results": results,
        }
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
