#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import filecmp
import json
from pathlib import Path
import re
import shutil
import sys


ROOT_FILES = (
    "AGENTS.md",
    "USAGE.md",
    "agent.md",
    "brain.schema.yaml",
    "run_brain.sh",
)

ROOT_DIRS = (
    ".github",
    "capabilities",
    "memory",
    "orchestrator",
    "schemas",
    "scripts",
    "simulation",
    "telemetry",
    "training",
)

BACKUP_DIR = ".agenticswarm-backups"
MANIFEST_PATH = ".agenticswarm-install.json"

AUDIT_REPORT_TEMPLATE = """version: "1.0"
last_updated: "{date}"
description: Audit reports emitted by the single-entry audit runner.

reports: []

notes:
  - Each report captures discovery counts, validation status, and the phases executed by `scripts/run_audit.py`.
"""

DISCOVERY_STATE_TEMPLATE = """version: "1.0"
last_updated: "{date}"
description: Persistent discovery watch state used for startup rechecks and new-install detection.

state:
  repo_root: ""
  last_full_audit_at: null
  last_startup_check_at: null
  watch_roots: []
  fingerprints: {{}}
  discovery_counts: {{}}
  last_change_detected: false
  last_change_summary: []

notes:
  - "run_audit.py --startup-check compares current watch-root fingerprints with this state."
  - "If a watched path changes, the audit runner performs a full refresh and repopulates the registries."
"""

AUTOPILOT_STATE_TEMPLATE = """version: "1.0"
last_updated: "{date}"
description: Persisted autopilot installation and maintenance state.

state:
  enabled: true
  autostart_installed: false
  autostart_platform: null
  autostart_label: null
  autostart_path: null
  last_install_attempt_at: null
  last_install_status: never_attempted
  last_install_error: null
  last_maintenance_run_at: null
  last_maintenance_summary: []
  last_git_check_at: null
  last_git_branch: null
  last_git_head_sha: null
  last_git_upstream_ref: null
  last_git_upstream_head_sha: null
  last_git_ahead_count: 0
  last_git_behind_count: 0
  last_git_dirty: false
  last_featureset_update_at: null
  last_featureset_update_status: never_checked
  last_featureset_update_reason: null

notes:
  - This file records whether the brain successfully installed a background startup recheck adapter.
"""

ROUTES_TEMPLATE = """version: "1.0"
last_updated: "{date}"
description: Route telemetry store for replay, structural plasticity, and model-tier optimization.

routes: []
route_preferences: []
plasticity_recommendations: []
training_triplets: []

notes:
  - Append route records here or partition by date in larger repositories.
  - Use `route_preferences` to store verified high-signal route summaries for replay-aware planning.
  - Use `plasticity_recommendations` for merge and prune proposals before applying topology changes.
"""

BLACKBOARD_TEMPLATE = """version: "1.0"
last_updated: "{date}"
description: Shared event log for task coordination, routing, approvals, and critic outcomes.

events: []

notes:
  - Events in this file are append-only coordination facts emitted by the execution engine.
"""

CONTROL_PLANE_TEMPLATE = """version: "1.0"
last_updated: "{date}"
description: File-first control plane for tasks, runs, approvals, artifacts, leases, queues, and workers.

tasks: []
runs: []
approvals: []
artifacts: []
leases: []
queue_items: []
workers: []

notes:
  - This file is the durable control-plane state for guarded-autonomy execution.
"""

BRAIN_NETWORK_INSTALLS_TEMPLATE = """version: "1.0"
last_updated: "{date}"
description: Durable install and activation state for curated brain-network integrations.

installs: []
benchmarks: []

notes:
  - Each install record tracks local install feasibility, activation status, and benchmark snapshots.
"""

USER_PROFILE_TEMPLATE = """version: "1.0"
last_updated: "{date}"
description: Portable sovereign-brain profile for personal taste, judgment, autonomy, and acceptance signals.

user_taste_profile:
  design_preferences: []
  technical_standards: []
  product_ambition: balanced_excellence
  risk_tolerance: guarded_high_autonomy
  refinement_style: meticulous
  quality_target_preferences: {{}}
  task_family_preferences: {{}}

product_judgment_profile:
  architecture_priority: 0.8
  ux_priority: 0.8
  reliability_priority: 0.85
  clarity_priority: 0.8
  polish_priority: 0.75
  distinctiveness_priority: 0.7
  accepted_work_count: 0
  rejected_work_count: 0
  edited_work_count: 0
  reverted_work_count: 0
  reused_work_count: 0

autonomy_profile:
  mode: guarded_high_autonomy
  auto_execute_task_classes:
    - documentation_refinement
    - quality_hardening
    - consistency_fix
    - benchmark_refresh
  approval_required_for:
    - destructive_actions
    - production_deployment
    - security_sensitive_operations
    - major_product_direction_change
  meticulous_task_bias: high

acceptance_signals: []

notes:
  - This file stores portable user-owned intelligence that may survive repo transplants.
"""

PRODUCT_CONTEXT_TEMPLATE = """version: "1.0"
last_updated: "{date}"
description: Repo-local product context for ontology, product intent, quality model, and ranked opportunities.

product_intent_graph:
  repo_name: ""
  goal_summary: ""
  target_users: []
  feature_priorities: []
  differentiators: []
  constraints: []
  last_refreshed_at: null

product_quality_model:
  architecture_quality: 0.5
  ux_quality: 0.5
  reliability: 0.5
  maintainability: 0.5
  clarity: 0.5
  polish: 0.5
  distinctiveness: 0.5
  last_refreshed_at: null

repo_ontology:
  repo_fingerprint: ""
  repo_name: ""
  stack: []
  risk_level: medium
  file_count: 0
  modules: []
  domains: []
  workflows: []
  user_facing_surfaces: []
  architecture_relationships: []
  last_refreshed_at: null

opportunity_map: []

notes:
  - This file is repo-bound and should be rebuilt after transplant into a new repository.
"""

PORTABLE_MEMORY_TEMPLATE = """version: "1.0"
last_updated: "{date}"
description: Portable and derived-portable sovereign-brain memory, route preferences, and capability preferences.

memory_classification_policy:
  portable_classes:
    - user_profile
    - general_quality_pattern
    - general_capability_preference
    - portable_route_preference
  repo_bound_classes:
    - repo_fact
    - repo_conflict
    - control_plane_state
    - blackboard_event
    - repo_route_record
    - repo_runtime_registry
    - repo_install_snapshot
  derived_portable_classes:
    - derived_portable_lesson
    - scrubbed_route_pattern

portable_memory: []
derived_portable_lessons: []
portable_route_preferences: []
capability_preferences: []

notes:
  - Portable intelligence must not include repo names, file paths, task IDs, or artifact bodies.
"""

TRANSPLANT_HISTORY_TEMPLATE = """version: "1.0"
last_updated: "{date}"
description: Transplant history for sovereign-brain carryover across repositories.

transplants: []

notes:
  - Each entry records the portable payload transferred into a target repo and the sections stripped as repo-bound.
"""


def now_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def backup_path(target_root: Path, relative: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return target_root / BACKUP_DIR / timestamp / relative


def maybe_backup(target_root: Path, relative: Path) -> None:
    destination = target_root / relative
    if not destination.exists():
        return
    source = Path(__file__).resolve().parent / relative
    try:
        same = filecmp.cmp(source, destination, shallow=False)
    except OSError:
        same = False
    if same:
        return
    backup = backup_path(target_root, relative)
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(destination, backup)


def install_path(source_root: Path, target_root: Path, relative: str) -> None:
    src = source_root / relative
    dst = target_root / relative
    if src.is_dir():
        for child in src.rglob("*"):
            if child.is_dir():
                continue
            child_relative = child.relative_to(source_root)
            maybe_backup(target_root, child_relative)
            copy_file(child, target_root / child_relative)
        return
    maybe_backup(target_root, Path(relative))
    copy_file(src, dst)


def merge_gitignore(source_root: Path, target_root: Path) -> None:
    required_lines = (source_root / ".gitignore").read_text(encoding="utf-8").splitlines()
    required_lines.append(f"{BACKUP_DIR}/")
    target_path = target_root / ".gitignore"
    existing = target_path.read_text(encoding="utf-8").splitlines() if target_path.exists() else []
    merged = list(existing)
    for line in required_lines:
        if line not in merged:
            merged.append(line)
    target_path.write_text("\n".join(merged).rstrip() + "\n", encoding="utf-8")


def reset_brain_manifest(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^    name:.*$", "    name: ''", text)
    text = re.sub(r"(?ms)^    stack:.*?(?=^    [A-Za-z_])", "    stack: []\n", text)
    text = re.sub(r"(?ms)\n  discovery_summary:.*$", "", text)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def reset_section_list(path: Path, key: str, next_key: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = rf"(?ms)^{re.escape(key)}:.*?(?=^{re.escape(next_key)}:)"
    replacement = f"{key}: []\n\n"
    text = re.sub(pattern, replacement, text)
    path.write_text(text, encoding="utf-8")


def reset_stateful_files(target_root: Path) -> None:
    reset_brain_manifest(target_root / "brain.schema.yaml")
    reset_section_list(target_root / "capabilities/agents.yaml", "agents", "notes")
    reset_section_list(target_root / "capabilities/skills.yaml", "skills", "notes")
    reset_section_list(target_root / "capabilities/plugins.yaml", "plugins", "notes")
    reset_section_list(target_root / "capabilities/mcp.yaml", "mcp_entries", "notes")
    reset_section_list(target_root / "capabilities/cli.yaml", "cli_entries", "notes")
    reset_section_list(target_root / "capabilities/models.yaml", "models", "notes")
    reset_section_list(target_root / "capabilities/runtime.yaml", "agent_executors", "model_routers")
    reset_section_list(target_root / "capabilities/runtime.yaml", "model_routers", "tool_backends")
    reset_section_list(target_root / "capabilities/runtime.yaml", "tool_backends", "notes")

    (target_root / "telemetry/audit_report.yaml").write_text(
        AUDIT_REPORT_TEMPLATE.format(date=now_date()),
        encoding="utf-8",
    )
    (target_root / "telemetry/discovery_state.yaml").write_text(
        DISCOVERY_STATE_TEMPLATE.format(date=now_date()),
        encoding="utf-8",
    )
    (target_root / "telemetry/autopilot_state.yaml").write_text(
        AUTOPILOT_STATE_TEMPLATE.format(date=now_date()),
        encoding="utf-8",
    )
    (target_root / "telemetry/routes.yaml").write_text(
        ROUTES_TEMPLATE.format(date=now_date()),
        encoding="utf-8",
    )
    (target_root / "telemetry/blackboard.yaml").write_text(
        BLACKBOARD_TEMPLATE.format(date=now_date()),
        encoding="utf-8",
    )
    (target_root / "telemetry/control_plane.yaml").write_text(
        CONTROL_PLANE_TEMPLATE.format(date=now_date()),
        encoding="utf-8",
    )
    (target_root / "telemetry/brain_network_installs.yaml").write_text(
        BRAIN_NETWORK_INSTALLS_TEMPLATE.format(date=now_date()),
        encoding="utf-8",
    )
    (target_root / "memory/user_profile.yaml").write_text(
        USER_PROFILE_TEMPLATE.format(date=now_date()),
        encoding="utf-8",
    )
    (target_root / "memory/product_context.yaml").write_text(
        PRODUCT_CONTEXT_TEMPLATE.format(date=now_date()),
        encoding="utf-8",
    )
    (target_root / "memory/portable_memory.yaml").write_text(
        PORTABLE_MEMORY_TEMPLATE.format(date=now_date()),
        encoding="utf-8",
    )
    (target_root / "telemetry/transplant_history.yaml").write_text(
        TRANSPLANT_HISTORY_TEMPLATE.format(date=now_date()),
        encoding="utf-8",
    )


def write_manifest(source_root: Path, target_root: Path) -> None:
    manifest = {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(source_root),
        "target_root": str(target_root),
        "installed_paths": list(ROOT_FILES) + list(ROOT_DIRS),
    }
    (target_root / MANIFEST_PATH).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def install_scaffold(source_root: Path, target_root: Path) -> None:
    for relative in ROOT_FILES + ROOT_DIRS:
        install_path(source_root, target_root, relative)

    merge_gitignore(source_root, target_root)
    reset_stateful_files(target_root)
    write_manifest(source_root, target_root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the AgenticSwarm brain scaffold into a target repository.")
    parser.add_argument("--target", default=".", help="Target repository root.")
    args = parser.parse_args()

    source_root = Path(__file__).resolve().parent
    target_root = Path(args.target).resolve()

    if source_root == target_root:
        print("Refusing to install into the source scaffold repository.", file=sys.stderr)
        return 1
    if not target_root.exists():
        print(f"Target path does not exist: {target_root}", file=sys.stderr)
        return 1
    if not target_root.is_dir():
        print(f"Target path is not a directory: {target_root}", file=sys.stderr)
        return 1

    install_scaffold(source_root, target_root)

    print(f"Installed AgenticSwarm scaffold into {target_root}")
    print("Next steps:")
    print("  1. ./run_brain.sh --dry-run")
    print("  2. ./run_brain.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
