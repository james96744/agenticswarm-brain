from __future__ import annotations

import argparse
from datetime import datetime, timezone

try:
    from brain_utils import dump_yaml_file, load_yaml_file, repo_root_from
    from runtime_bridge import build_runtime_registry, plan_execution
except ModuleNotFoundError:
    from scripts.brain_utils import dump_yaml_file, load_yaml_file, repo_root_from
    from scripts.runtime_bridge import build_runtime_registry, plan_execution


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a dry simulation of routing policy against sample scenarios.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    scenarios = load_yaml_file(root / "simulation/scenarios.yaml").get("scenarios", [])
    policies = load_yaml_file(root / "orchestrator/policies.yaml")
    runtime_registry = build_runtime_registry(root, write=not args.dry_run)
    telemetry = load_yaml_file(root / "telemetry/routes.yaml")
    routes = telemetry.setdefault("routes", [])

    simulated = []
    for scenario in scenarios:
        plan = plan_execution(root, scenario, runtime_registry=runtime_registry, policies=policies)
        simulated.append(
            {
                "task_id": scenario["scenario_id"],
                "task_family": scenario["task_family"],
                "simulated": True,
                "model_tier_path": plan["model_tier_path"],
                "executor_id": plan["selected_executor"]["executor_id"] if plan.get("selected_executor") else None,
                "router_id": plan["selected_router"]["router_id"] if plan.get("selected_router") else None,
                "backend_ids": [backend["backend_id"] for backend in plan.get("backend_bundle", [])],
                "plan_confidence": plan.get("confidence"),
                "unresolved": plan.get("unresolved", []),
                "quality_target": scenario.get("quality_target", "balanced"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    if args.dry_run:
        for item in simulated:
            print(item)
        return 0

    routes.extend(simulated)
    dump_yaml_file(root / "telemetry/routes.yaml", telemetry)
    print(f"Wrote {len(simulated)} simulated routes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
