from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone

try:
    from brain_utils import dump_yaml_file, load_yaml_file, repo_root_from
except ModuleNotFoundError:
    from scripts.brain_utils import dump_yaml_file, load_yaml_file, repo_root_from


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect contradictory facts and write memory conflict records.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    facts_data = load_yaml_file(root / "memory/facts.yaml")
    conflicts_data = load_yaml_file(root / "memory/conflicts.yaml")
    facts = facts_data.get("facts", [])

    grouped = defaultdict(list)
    for fact in facts:
        subject = fact.get("subject")
        predicate = fact.get("predicate")
        if subject and predicate:
            grouped[(subject, predicate)].append(fact)

    detected = []
    for (subject, predicate), entries in grouped.items():
        values = {entry.get("object") for entry in entries}
        if len(values) > 1:
            detected.append(
                {
                    "conflict_id": f"{subject}:{predicate}",
                    "subject": subject,
                    "predicate": predicate,
                    "candidate_values": sorted(value for value in values if value is not None),
                    "sources": [entry.get("source", "unknown") for entry in entries],
                    "status": "needs_reconciliation",
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    if args.dry_run:
        for item in detected:
            print(item)
        return 0

    conflicts_data["conflicts"] = detected
    dump_yaml_file(root / "memory/conflicts.yaml", conflicts_data)
    print(f"Wrote {len(detected)} memory conflicts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
