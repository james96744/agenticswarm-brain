from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

try:
    from brain_utils import dump_json_stdout, repo_root_from
    from bootstrap_brain import apply_discovery, collect_discovery
    from sovereign_memory import apply_transplant_payload, build_transplant_payload, ensure_state_files
    from validate_brain import run_validation
except ModuleNotFoundError:
    from scripts.brain_utils import dump_json_stdout, repo_root_from
    from scripts.bootstrap_brain import apply_discovery, collect_discovery
    from scripts.sovereign_memory import apply_transplant_payload, build_transplant_payload, ensure_state_files
    from scripts.validate_brain import run_validation


def _source_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _install_scaffold(source_root: Path, target_root: Path) -> None:
    install_path = source_root / "install_brain.py"
    spec = importlib.util.spec_from_file_location("install_brain_module", install_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load install scaffold module from {install_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.install_scaffold(source_root, target_root)


def run_target_audit(target_root: Path) -> dict:
    command = [
        sys.executable,
        str(target_root / "scripts" / "run_audit.py"),
        "--repo-root",
        str(target_root),
        "--dry-run",
        "--no-autostart",
    ]
    completed = subprocess.run(command, cwd=target_root, capture_output=True, text=True, check=False)
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "status": "passed" if completed.returncode == 0 else "failed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Implant the sovereign brain into another local repo while carrying portable intelligence only.")
    parser.add_argument("--repo-root", default=None, help="Source repository root. Defaults to the current repo.")
    parser.add_argument("--target", required=True, help="Existing local target repository root.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source_root = repo_root_from(args.repo_root)
    target_root = Path(args.target).resolve()
    scaffold_root = _source_root()

    if source_root == target_root:
        print("Refusing to transplant into the same repository.", file=sys.stderr)
        return 1
    if not target_root.exists():
        print(f"Target path does not exist: {target_root}", file=sys.stderr)
        return 1
    if not target_root.is_dir():
        print(f"Target path is not a directory: {target_root}", file=sys.stderr)
        return 1

    ensure_state_files(source_root)
    source_errors = run_validation(source_root)
    if source_errors:
        dump_json_stdout({"status": "blocked", "reason": "source_validation_failed", "errors": source_errors})
        return 1

    payload = build_transplant_payload(source_root, target_root)
    if args.dry_run:
        dump_json_stdout(
            {
                "status": "dry_run",
                "source_repo": str(source_root),
                "target_repo": str(target_root),
                "carried_sections": payload.get("carried_sections", []),
                "stripped_sections": payload.get("stripped_sections", []),
                "payload_summary": payload.get("summary", {}),
                "portable_memory": len(payload.get("portable_memory", [])),
                "derived_portable_lessons": len(payload.get("derived_portable_lessons", [])),
                "portable_route_preferences": len(payload.get("portable_route_preferences", [])),
                "capability_preferences": len(payload.get("capability_preferences", [])),
            }
        )
        return 0

    _install_scaffold(scaffold_root, target_root)
    ensure_state_files(target_root)
    apply_transplant_payload(target_root, payload)

    discovery = collect_discovery(target_root)
    apply_discovery(target_root, discovery)
    audit = run_target_audit(target_root)
    target_errors = run_validation(target_root)

    success = not target_errors
    status = "completed" if success and audit["returncode"] == 0 else ("completed_with_warnings" if success else "completed_with_issues")
    dump_json_stdout(
        {
            "status": status,
            "source_repo": str(source_root),
            "target_repo": str(target_root),
            "carried_sections": payload.get("carried_sections", []),
            "stripped_sections": payload.get("stripped_sections", []),
            "payload_summary": payload.get("summary", {}),
            "audit": audit,
            "target_validation_errors": target_errors,
        }
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
