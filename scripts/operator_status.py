from __future__ import annotations

import argparse

try:
    from brain_utils import dump_json_stdout, load_yaml_file, repo_root_from
except ModuleNotFoundError:
    from scripts.brain_utils import dump_json_stdout, load_yaml_file, repo_root_from


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize runtime health, recent runs, approvals, and replay readiness.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Accepted for audit compatibility; output is always read-only.")
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    runtime = load_yaml_file(root / "capabilities/runtime.yaml")
    control_plane = load_yaml_file(root / "telemetry/control_plane.yaml")
    routes = load_yaml_file(root / "telemetry/routes.yaml")
    benchmarks = load_yaml_file(root / "capabilities/benchmarks.yaml")

    approvals = control_plane.get("approvals", [])
    runs = control_plane.get("runs", [])
    recent_runs = sorted(runs, key=lambda item: item.get("updated_at", ""), reverse=True)[:5]

    payload = {
        "runtime": {
            "executors_ready": len([item for item in runtime.get("agent_executors", []) if item.get("health_status") == "ready"]),
            "routers_ready": len([item for item in runtime.get("model_routers", []) if item.get("health_status") == "ready"]),
            "backends_ready": len([item for item in runtime.get("tool_backends", []) if item.get("health_status") == "ready"]),
        },
        "approvals": {
            "pending": len([item for item in approvals if item.get("state") == "pending"]),
            "approved": len([item for item in approvals if item.get("state") == "approved"]),
            "rejected": len([item for item in approvals if item.get("state") == "rejected"]),
        },
        "runs": {
            "total": len(runs),
            "recent": recent_runs,
        },
        "learning": {
            "route_records": len(routes.get("routes", [])),
            "replay_candidates": len([item for item in routes.get("routes", []) if item.get("replay_eligible")]),
            "task_family_benchmarks": len(benchmarks.get("task_family_benchmarks", [])),
            "training_triplets": len(routes.get("training_triplets", [])),
        },
    }
    dump_json_stdout(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
