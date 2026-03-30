from __future__ import annotations

import argparse

try:
    from brain_utils import dump_json_stdout, load_yaml_file, repo_root_from
    from remote_transport import RemoteFabricTransport
except ModuleNotFoundError:
    from scripts.brain_utils import dump_json_stdout, load_yaml_file, repo_root_from
    from scripts.remote_transport import RemoteFabricTransport


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
    policies = load_yaml_file(root / "orchestrator/policies.yaml")
    transport = RemoteFabricTransport(root)
    packaging_profile = policies.get("packaging_profile", {})
    active_tier = packaging_profile.get("active_tier", "community")
    tier_config = packaging_profile.get("tiers", {}).get(active_tier, {})

    approvals = control_plane.get("approvals", [])
    runs = control_plane.get("runs", [])
    queue_items = control_plane.get("queue_items", [])
    workers = control_plane.get("workers", [])
    verified_routes = [item for item in routes.get("routes", []) if item.get("verified_execution")]
    recent_runs = sorted(runs, key=lambda item: item.get("updated_at", ""), reverse=True)[:5]

    payload = {
        "runtime": {
            "executors_ready": len([item for item in runtime.get("agent_executors", []) if item.get("health_status") == "ready"]),
            "routers_ready": len([item for item in runtime.get("model_routers", []) if item.get("health_status") == "ready"]),
            "backends_ready": len([item for item in runtime.get("tool_backends", []) if item.get("health_status") == "ready"]),
        },
        "packaging": {
            "active_tier": active_tier,
            "allows_external_services": bool(tier_config.get("allows_external_services", False)),
            "byo_infrastructure": bool(tier_config.get("byo_infrastructure", False)),
            "allowed_remote_transport_modes": tier_config.get("allowed_remote_transport_modes", ["shared_filesystem_fabric"]),
        },
        "approvals": {
            "pending": len([item for item in approvals if item.get("state") == "pending"]),
            "approved": len([item for item in approvals if item.get("state") == "approved"]),
            "rejected": len([item for item in approvals if item.get("state") == "rejected"]),
            "expired": len([item for item in approvals if item.get("state") == "expired"]),
        },
        "runs": {
            "total": len(runs),
            "recent": recent_runs,
        },
        "scheduler": {
            "pending": len([item for item in queue_items if item.get("state") == "pending"]),
            "claimed": len([item for item in queue_items if item.get("state") == "claimed"]),
            "dispatched": len([item for item in queue_items if item.get("state") == "dispatched"]),
            "awaiting_approval": len([item for item in queue_items if item.get("state") == "awaiting_approval"]),
            "completed": len([item for item in queue_items if item.get("state") == "completed"]),
            "failed": len([item for item in queue_items if item.get("state") == "failed"]),
            "workers": workers,
        },
        "transport": transport.status(),
        "learning": {
            "route_records": len(routes.get("routes", [])),
            "route_preferences": len(routes.get("route_preferences", [])),
            "replay_candidates": len([item for item in routes.get("routes", []) if item.get("replay_eligible")]),
            "verified_executions": len(verified_routes),
            "avg_replay_score": round(
                sum(float(item.get("replay_score", 0.0)) for item in verified_routes)
                / max(1, len(verified_routes)),
                4,
            ),
            "task_family_benchmarks": len(benchmarks.get("task_family_benchmarks", [])),
            "adapter_benchmarks": len(benchmarks.get("adapter_benchmarks", [])),
            "training_triplets": len(routes.get("training_triplets", [])),
        },
    }
    dump_json_stdout(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
