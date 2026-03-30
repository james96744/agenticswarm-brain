from __future__ import annotations

import argparse

try:
    from brain_utils import dump_json_stdout, load_yaml_file, repo_root_from
    from remote_transport import RemoteFabricTransport
    from runtime_bridge import curated_integrations, match_curated_capability
    from sovereign_memory import ensure_state_files, transplant_summary
except ModuleNotFoundError:
    from scripts.brain_utils import dump_json_stdout, load_yaml_file, repo_root_from
    from scripts.remote_transport import RemoteFabricTransport
    from scripts.runtime_bridge import curated_integrations, match_curated_capability
    from scripts.sovereign_memory import ensure_state_files, transplant_summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize runtime health, recent runs, approvals, and replay readiness.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Accepted for audit compatibility; output is always read-only.")
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    ensure_state_files(root)
    runtime = load_yaml_file(root / "capabilities/runtime.yaml")
    control_plane = load_yaml_file(root / "telemetry/control_plane.yaml")
    routes = load_yaml_file(root / "telemetry/routes.yaml")
    benchmarks = load_yaml_file(root / "capabilities/benchmarks.yaml")
    brain_network = load_yaml_file(root / "capabilities/brain_network.yaml")
    skills = load_yaml_file(root / "capabilities/skills.yaml")
    plugins = load_yaml_file(root / "capabilities/plugins.yaml")
    mcp = load_yaml_file(root / "capabilities/mcp.yaml")
    cli = load_yaml_file(root / "capabilities/cli.yaml")
    install_profiles = load_yaml_file(root / "capabilities/brain_network_install_profiles.yaml")
    install_state = load_yaml_file(root / "telemetry/brain_network_installs.yaml")
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
    curated = curated_integrations(brain_network)
    adopted_ids = sorted({
        match.get("integration_id")
        for collection in (
            runtime.get("tool_backends", []),
            skills.get("skills", []),
            plugins.get("plugins", []),
            mcp.get("mcp_entries", []),
            cli.get("cli_entries", []),
        )
        for item in collection
        for match in [match_curated_capability(item, curated)]
        if match
    })
    bundle_counts = {
        bundle.get("bundle_id"): len(bundle.get("integration_ids", []))
        for bundle in brain_network.get("bundles", [])
    }
    installs = install_state.get("installs", [])
    latest_benchmark = sorted(install_state.get("benchmarks", []), key=lambda item: item.get("captured_at", ""), reverse=True)[:1]
    installable_profiles = install_profiles.get("profiles", [])
    sovereign_summary = transplant_summary(root)
    user_profile = load_yaml_file(root / "memory/user_profile.yaml")
    product_context = load_yaml_file(root / "memory/product_context.yaml")

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
        "brain_network": {
            "curated_integrations": len(curated),
            "adopted_integrations": len(adopted_ids),
            "adopted_integration_ids": adopted_ids,
            "bundles": bundle_counts,
            "install_profiles": len(installable_profiles),
            "installed_integrations": len([item for item in installs if item.get("status") in {"installed", "activated", "installed_assets_only"}]),
            "activated_integrations": len([item for item in installs if item.get("status") == "activated"]),
            "blocked_integrations": len([item for item in installs if item.get("status") == "blocked"]),
            "latest_benchmark": latest_benchmark[0] if latest_benchmark else None,
        },
        "learning": {
            "route_records": len(routes.get("routes", [])),
            "route_preferences": len(routes.get("route_preferences", [])),
            "replay_candidates": len([item for item in routes.get("routes", []) if item.get("replay_eligible")]),
            "verified_executions": len(verified_routes),
            "avg_total_tokens_verified": round(
                sum(float(item.get("total_tokens", 0.0)) for item in verified_routes)
                / max(1, len(verified_routes)),
                2,
            ),
            "avg_prompt_tokens_verified": round(
                sum(float(item.get("prompt_tokens", 0.0)) for item in verified_routes)
                / max(1, len(verified_routes)),
                2,
            ),
            "avg_replay_score": round(
                sum(float(item.get("replay_score", 0.0)) for item in verified_routes)
                / max(1, len(verified_routes)),
                4,
            ),
            "task_family_benchmarks": len(benchmarks.get("task_family_benchmarks", [])),
            "adapter_benchmarks": len(benchmarks.get("adapter_benchmarks", [])),
            "training_triplets": len(routes.get("training_triplets", [])),
        },
        "sovereign_brain": {
            "autonomy_mode": user_profile.get("autonomy_profile", {}).get("mode"),
            "accepted_work_count": int(user_profile.get("product_judgment_profile", {}).get("accepted_work_count", 0)),
            "rejected_work_count": int(user_profile.get("product_judgment_profile", {}).get("rejected_work_count", 0)),
            "repo_goal_summary": product_context.get("product_intent_graph", {}).get("goal_summary"),
            "opportunity_count": len(product_context.get("opportunity_map", [])),
            **sovereign_summary,
        },
    }
    dump_json_stdout(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
