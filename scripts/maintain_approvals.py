from __future__ import annotations

import argparse

try:
    from brain_utils import dump_json_stdout, load_yaml_file, repo_root_from
    from control_plane import ControlPlaneStore
except ModuleNotFoundError:
    from scripts.brain_utils import dump_json_stdout, load_yaml_file, repo_root_from
    from scripts.control_plane import ControlPlaneStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Expire stale pending approvals and summarize approval state.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stale-after-minutes", type=int, default=None)
    parser.add_argument("--actor", default="brainstem-maintenance")
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    policies = load_yaml_file(root / "orchestrator" / "policies.yaml")
    approval_policy = policies.get("approval_policy", {})
    stale_after = args.stale_after_minutes or int(approval_policy.get("stale_after_minutes", 30))
    control_plane = ControlPlaneStore(root)

    if args.dry_run:
        approvals = control_plane.get_items("approvals")
        dump_json_stdout(
            {
                "stale_after_minutes": stale_after,
                "pending": len([item for item in approvals if item.get("state") == "pending"]),
                "expired": len([item for item in approvals if item.get("state") == "expired"]),
            }
        )
        return 0

    expired = control_plane.expire_stale_approvals(
        stale_after_minutes=stale_after,
        actor=args.actor,
        note=f"Expired automatically after {stale_after} minutes without approval.",
    )
    approvals = control_plane.get_items("approvals")
    dump_json_stdout(
        {
            "stale_after_minutes": stale_after,
            "expired_count": len(expired),
            "expired_approval_ids": [item.get("approval_id") for item in expired],
            "pending": len([item for item in approvals if item.get("state") == "pending"]),
            "expired": len([item for item in approvals if item.get("state") == "expired"]),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
