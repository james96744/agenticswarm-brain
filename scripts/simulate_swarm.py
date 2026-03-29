from __future__ import annotations

import argparse
from datetime import datetime, timezone

try:
    from brain_utils import dump_yaml_file, load_yaml_file, repo_root_from
except ModuleNotFoundError:
    from scripts.brain_utils import dump_yaml_file, load_yaml_file, repo_root_from


RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
COMPLEXITY_ORDER = {"low": 0, "medium": 1, "high": 2}


def build_route(scenario: dict, policies: dict) -> list[str]:
    route = []
    if policies.get("routing_policy", {}).get("semantic_router_enabled", False):
        route.append("tier_0_router")
    route.append("tier_1_worker")

    risk = RISK_ORDER.get(scenario.get("risk_level", "medium"), 1)
    complexity = COMPLEXITY_ORDER.get(scenario.get("complexity", "medium"), 1)

    critic_needed = scenario.get("requires_code", False) or scenario.get("requires_tools", False) or risk >= 1
    if critic_needed:
        route.append("tier_2_critic")

    expert_needed = scenario.get("force_expert", False) or scenario.get("high_stakes", False) or risk >= 2 or complexity >= 2
    if expert_needed:
        route.append("tier_3_expert")

    return route


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a dry simulation of routing policy against sample scenarios.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    scenarios = load_yaml_file(root / "simulation/scenarios.yaml").get("scenarios", [])
    policies = load_yaml_file(root / "orchestrator/policies.yaml")
    telemetry = load_yaml_file(root / "telemetry/routes.yaml")
    routes = telemetry.setdefault("routes", [])

    simulated = []
    for scenario in scenarios:
        route = build_route(scenario, policies)
        simulated.append(
            {
                "task_id": scenario["scenario_id"],
                "task_family": scenario["task_family"],
                "simulated": True,
                "model_tier_path": route,
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
