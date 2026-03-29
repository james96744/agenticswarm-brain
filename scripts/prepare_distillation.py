from __future__ import annotations

import argparse
from collections import defaultdict

try:
    from brain_utils import dump_yaml_file, load_yaml_file, repo_root_from
except ModuleNotFoundError:
    from scripts.brain_utils import dump_yaml_file, load_yaml_file, repo_root_from


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare adapter training jobs from verified expert-correction triplets.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    telemetry = load_yaml_file(root / "telemetry/routes.yaml")
    policies = load_yaml_file(root / "orchestrator/policies.yaml")
    jobs_data = load_yaml_file(root / "training/jobs.yaml")
    adapters_data = load_yaml_file(root / "training/adapters.yaml")

    trigger_count = policies.get("meta_critic_fine_tuning_policy", {}).get("lora_trigger_min_examples", 50)
    synthetic_target = policies.get("meta_critic_fine_tuning_policy", {}).get("synthetic_expansion_target", 500)

    grouped = defaultdict(list)
    for triplet in telemetry.get("training_triplets", []):
        if triplet.get("verified", False):
            grouped[triplet.get("task_family", "unknown")].append(triplet)

    jobs = []
    adapters = adapters_data.get("adapters", [])
    existing_adapter_ids = {adapter.get("adapter_id") for adapter in adapters}

    for task_family, items in grouped.items():
        if len(items) < trigger_count:
            continue
        adapter_id = f"{task_family}-lora"
        jobs.append(
            {
                "job_id": f"distill-{task_family}",
                "task_family": task_family,
                "verified_examples": len(items),
                "synthetic_expansion_target": synthetic_target,
                "status": "ready_for_training",
            }
        )
        if adapter_id not in existing_adapter_ids:
            adapters.append(
                {
                    "adapter_id": adapter_id,
                    "task_family": task_family,
                    "status": "planned",
                    "activation_policy": "require_benchmark_pass",
                }
            )

    if args.dry_run:
        for job in jobs:
            print(job)
        return 0

    jobs_data["jobs"] = jobs
    adapters_data["adapters"] = adapters
    dump_yaml_file(root / "training/jobs.yaml", jobs_data)
    dump_yaml_file(root / "training/adapters.yaml", adapters_data)
    print(f"Prepared {len(jobs)} distillation jobs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
