from __future__ import annotations

import argparse
from datetime import datetime, timezone
import time

try:
    from brain_utils import dump_json_stdout, dump_yaml_file, file_lock, load_yaml_file, repo_root_from
    from runtime_bridge import curated_integrations, match_curated_backend, match_curated_capability, plan_execution
except ModuleNotFoundError:
    from scripts.brain_utils import dump_json_stdout, dump_yaml_file, file_lock, load_yaml_file, repo_root_from
    from scripts.runtime_bridge import curated_integrations, match_curated_backend, match_curated_capability, plan_execution


SCENARIOS = [
    {
        "scenario_id": "architecture",
        "task_family": "architecture_decision",
        "quality_target": "high",
        "complexity": "high",
        "requires_tools": True,
    },
    {
        "scenario_id": "coding",
        "task_family": "boilerplate_code",
        "quality_target": "balanced",
        "complexity": "medium",
        "requires_code": True,
        "requires_tools": True,
    },
    {
        "scenario_id": "remote_coordination",
        "task_family": "research",
        "quality_target": "balanced",
        "complexity": "medium",
        "requires_tools": True,
        "dispatch_mode": "remote_worker",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_profiles(root):
    payload = load_yaml_file(root / "capabilities/brain_network_install_profiles.yaml")
    return {
        item.get("integration_id"): item
        for item in payload.get("profiles", [])
        if item.get("integration_id")
    }


def snapshot(root):
    runtime = load_yaml_file(root / "capabilities/runtime.yaml")
    routes = load_yaml_file(root / "telemetry/routes.yaml")
    benchmarks = load_yaml_file(root / "capabilities/benchmarks.yaml")
    brain_network = load_yaml_file(root / "capabilities/brain_network.yaml")
    skills = load_yaml_file(root / "capabilities/skills.yaml")
    plugins = load_yaml_file(root / "capabilities/plugins.yaml")
    mcp = load_yaml_file(root / "capabilities/mcp.yaml")
    cli = load_yaml_file(root / "capabilities/cli.yaml")
    installs = load_yaml_file(root / "telemetry/brain_network_installs.yaml").get("installs", [])
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
    installed_ids = {
        item.get("integration_id")
        for item in installs
        if item.get("status") in {"installed", "activated", "installed_assets_only"}
    }
    active_ids = sorted(set(adopted_ids) | installed_ids)
    verified_routes = [item for item in routes.get("routes", []) if item.get("verified_execution")]
    avg_total_tokens_verified = round(
        sum(float(item.get("total_tokens", 0.0)) for item in verified_routes) / max(1, len(verified_routes)),
        2,
    )
    avg_prompt_tokens_verified = round(
        sum(float(item.get("prompt_tokens", 0.0)) for item in verified_routes) / max(1, len(verified_routes)),
        2,
    )
    avg_completion_tokens_verified = round(
        sum(float(item.get("completion_tokens", 0.0)) for item in verified_routes) / max(1, len(verified_routes)),
        2,
    )
    avg_tool_context_tokens_verified = round(
        sum(float(item.get("tool_context_tokens", 0.0)) for item in verified_routes) / max(1, len(verified_routes)),
        2,
    )
    measured_token_routes = len([item for item in verified_routes if int(item.get("total_tokens", 0)) > 0])
    token_efficiency_score = round(1000.0 / max(1.0, avg_total_tokens_verified), 4)

    planned = []
    planning_latencies = []
    for scenario in SCENARIOS:
        started = time.perf_counter()
        route = plan_execution(root, dict(scenario))
        latency_ms = int((time.perf_counter() - started) * 1000)
        planning_latencies.append(latency_ms)
        selected_backend_ids = [item.get("backend_id") for item in route.get("backend_bundle", [])]
        curated_selected = sorted(
            {
                match.get("integration_id")
                for backend in route.get("backend_bundle", [])
                for match in [match_curated_backend(backend, curated)]
                if match
            }
        )
        planned.append(
            {
                "scenario_id": scenario["scenario_id"],
                "planning_latency_ms": latency_ms,
                "selected_executor_id": route.get("selected_executor", {}).get("executor_id"),
                "selected_router_id": route.get("selected_router", {}).get("router_id"),
                "selected_backend_ids": selected_backend_ids,
                "curated_selected": curated_selected,
                "reasons": route.get("reasons", []),
            }
        )

    return {
        "captured_at": utc_now(),
        "adopted_integrations": adopted_ids,
        "installed_integrations": sorted(installed_ids),
        "active_integrations": active_ids,
        "measured_token_routes": measured_token_routes,
        "token_efficiency_score": token_efficiency_score,
        "avg_total_tokens_verified": avg_total_tokens_verified,
        "avg_prompt_tokens_verified": avg_prompt_tokens_verified,
        "avg_completion_tokens_verified": avg_completion_tokens_verified,
        "avg_tool_context_tokens_verified": avg_tool_context_tokens_verified,
        "avg_planning_latency_ms": round(sum(planning_latencies) / max(1, len(planning_latencies)), 2),
        "avg_replay_score": round(
            sum(float(item.get("replay_score", 0.0)) for item in verified_routes) / max(1, len(verified_routes)),
            4,
        ),
        "route_records": len(routes.get("routes", [])),
        "verified_executions": len(verified_routes),
        "adapter_benchmarks": len(benchmarks.get("adapter_benchmarks", [])),
        "scenario_plans": planned,
    }


def append_benchmark(root, label: str, snapshot_payload: dict):
    path = root / "telemetry/brain_network_installs.yaml"
    with file_lock(path.with_suffix(path.suffix + ".lock")):
        payload = load_yaml_file(path)
        payload.setdefault("benchmarks", []).append({"label": label, **snapshot_payload})
        payload["last_updated"] = datetime.now(timezone.utc).date().isoformat()
        dump_yaml_file(path, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture benchmark snapshots for staged brain-network adoption.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--label", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    snap = snapshot(root)
    if not args.dry_run:
        append_benchmark(root, args.label, snap)
    dump_json_stdout({"label": args.label, **snap})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
