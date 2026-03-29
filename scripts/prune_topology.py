from __future__ import annotations

import argparse

try:
    from brain_utils import dump_yaml_file, load_yaml_file, repo_root_from
except ModuleNotFoundError:
    from scripts.brain_utils import dump_yaml_file, load_yaml_file, repo_root_from


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate agent merge and prune recommendations from benchmark telemetry.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    benchmarks = load_yaml_file(root / "capabilities/benchmarks.yaml")
    telemetry = load_yaml_file(root / "telemetry/routes.yaml")
    policies = load_yaml_file(root / "orchestrator/policies.yaml")

    thresholds = policies.get("structural_plasticity_policy", {})
    merge_when = thresholds.get("merge_when", {})
    prune_when = thresholds.get("prune_when", {})

    recommendations = []
    for pair in benchmarks.get("agent_pair_metrics", []):
        if (
            pair.get("mean_handoff_count", 0) >= merge_when.get("mean_handoff_count_gte", 999)
            and pair.get("mean_round_trip_latency_ratio", 0) >= merge_when.get("mean_round_trip_latency_ratio_gte", 999)
            and pair.get("task_family_success_rate", 0) >= merge_when.get("task_family_success_rate_gte", 999)
        ):
            recommendations.append(
                {
                    "type": "merge",
                    "task_family": pair.get("task_family"),
                    "agents": [pair.get("agent_a"), pair.get("agent_b")],
                    "reason": "High handoff overhead with acceptable success rate.",
                }
            )

    for metric in benchmarks.get("agent_value_metrics", []):
        if metric.get("prune_protected", False):
            continue
        if (
            metric.get("value_add_per_token", 1) <= prune_when.get("value_add_per_token_lte", -1)
            and metric.get("critic_rejection_rate", 0) >= prune_when.get("critic_rejection_rate_gte", 999)
            and metric.get("ignored_edit_rate", 0) >= prune_when.get("ignored_edit_rate_gte", 999)
        ):
            recommendations.append(
                {
                    "type": "prune",
                    "agent_id": metric.get("agent_id"),
                    "reason": "Low value-add with high rejection and ignored-edit rates.",
                }
            )

    if args.dry_run:
        for item in recommendations:
            print(item)
        return 0

    telemetry["plasticity_recommendations"] = recommendations
    dump_yaml_file(root / "telemetry/routes.yaml", telemetry)
    print(f"Wrote {len(recommendations)} plasticity recommendations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
