from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import re

try:
    from brain_utils import dump_yaml_file, iter_repo_files, load_yaml_file
except ModuleNotFoundError:
    from scripts.brain_utils import dump_yaml_file, iter_repo_files, load_yaml_file


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def date_now() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def repo_fingerprint(root: Path) -> str:
    digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()
    return digest[:16]


def user_profile_template() -> dict:
    return {
        "version": "1.0",
        "last_updated": date_now(),
        "description": "Portable sovereign-brain profile for personal taste, judgment, autonomy, and acceptance signals.",
        "user_taste_profile": {
            "design_preferences": [],
            "technical_standards": [],
            "product_ambition": "balanced_excellence",
            "risk_tolerance": "guarded_high_autonomy",
            "refinement_style": "meticulous",
            "quality_target_preferences": {},
            "task_family_preferences": {},
        },
        "product_judgment_profile": {
            "architecture_priority": 0.8,
            "ux_priority": 0.8,
            "reliability_priority": 0.85,
            "clarity_priority": 0.8,
            "polish_priority": 0.75,
            "distinctiveness_priority": 0.7,
            "accepted_work_count": 0,
            "rejected_work_count": 0,
            "edited_work_count": 0,
            "reverted_work_count": 0,
            "reused_work_count": 0,
        },
        "autonomy_profile": {
            "mode": "guarded_high_autonomy",
            "auto_execute_task_classes": [
                "documentation_refinement",
                "quality_hardening",
                "consistency_fix",
                "benchmark_refresh",
            ],
            "approval_required_for": [
                "destructive_actions",
                "production_deployment",
                "security_sensitive_operations",
                "major_product_direction_change",
            ],
            "meticulous_task_bias": "high",
        },
        "acceptance_signals": [],
        "notes": [
            "This file stores portable user-owned intelligence that may survive repo transplants.",
        ],
    }


def product_context_template() -> dict:
    return {
        "version": "1.0",
        "last_updated": date_now(),
        "description": "Repo-local product context for ontology, product intent, quality model, and ranked opportunities.",
        "product_intent_graph": {
            "repo_name": "",
            "goal_summary": "",
            "target_users": [],
            "feature_priorities": [],
            "differentiators": [],
            "constraints": [],
            "last_refreshed_at": None,
        },
        "product_quality_model": {
            "architecture_quality": 0.5,
            "ux_quality": 0.5,
            "reliability": 0.5,
            "maintainability": 0.5,
            "clarity": 0.5,
            "polish": 0.5,
            "distinctiveness": 0.5,
            "last_refreshed_at": None,
        },
        "repo_ontology": {
            "repo_fingerprint": "",
            "repo_name": "",
            "stack": [],
            "risk_level": "medium",
            "file_count": 0,
            "modules": [],
            "domains": [],
            "workflows": [],
            "user_facing_surfaces": [],
            "architecture_relationships": [],
            "last_refreshed_at": None,
        },
        "opportunity_map": [],
        "notes": [
            "This file is repo-bound and should be rebuilt after transplant into a new repository.",
        ],
    }


def portable_memory_template() -> dict:
    return {
        "version": "1.0",
        "last_updated": date_now(),
        "description": "Portable and derived-portable sovereign-brain memory, route preferences, and capability preferences.",
        "memory_classification_policy": {
            "portable_classes": [
                "user_profile",
                "general_quality_pattern",
                "general_capability_preference",
                "portable_route_preference",
            ],
            "repo_bound_classes": [
                "repo_fact",
                "repo_conflict",
                "control_plane_state",
                "blackboard_event",
                "repo_route_record",
                "repo_runtime_registry",
                "repo_install_snapshot",
            ],
            "derived_portable_classes": [
                "derived_portable_lesson",
                "scrubbed_route_pattern",
            ],
        },
        "portable_memory": [],
        "derived_portable_lessons": [],
        "portable_route_preferences": [],
        "capability_preferences": [],
        "notes": [
            "Portable intelligence must not include repo names, file paths, task IDs, or artifact bodies.",
        ],
    }


def transplant_history_template() -> dict:
    return {
        "version": "1.0",
        "last_updated": date_now(),
        "description": "Transplant history for sovereign-brain carryover across repositories.",
        "transplants": [],
        "notes": [
            "Each entry records the portable payload transferred into a target repo and the sections stripped as repo-bound.",
        ],
    }


def ensure_state_files(root: Path) -> None:
    defaults = {
        root / "memory/user_profile.yaml": user_profile_template(),
        root / "memory/product_context.yaml": product_context_template(),
        root / "memory/portable_memory.yaml": portable_memory_template(),
        root / "telemetry/transplant_history.yaml": transplant_history_template(),
    }
    for path, payload in defaults.items():
        if not path.exists():
            dump_yaml_file(path, payload)


def load_user_profile(root: Path) -> dict:
    ensure_state_files(root)
    return load_yaml_file(root / "memory/user_profile.yaml")


def load_product_context(root: Path) -> dict:
    ensure_state_files(root)
    return load_yaml_file(root / "memory/product_context.yaml")


def load_portable_memory(root: Path) -> dict:
    ensure_state_files(root)
    return load_yaml_file(root / "memory/portable_memory.yaml")


def load_transplant_history(root: Path) -> dict:
    ensure_state_files(root)
    return load_yaml_file(root / "telemetry/transplant_history.yaml")


def save_payload(path: Path, payload: dict) -> None:
    payload["last_updated"] = date_now()
    dump_yaml_file(path, payload)


def _bucket_preference(container: dict, key: str, value: str) -> None:
    if not value:
        return
    bucket = container.setdefault(key, {})
    bucket[value] = int(bucket.get(value, 0)) + 1


def record_execution_acceptance(root: Path, request, run, result) -> None:
    ensure_state_files(root)
    profile_path = root / "memory/user_profile.yaml"
    portable_path = root / "memory/portable_memory.yaml"
    profile = load_yaml_file(profile_path)
    portable = load_yaml_file(portable_path)

    success = result.status == "success" and result.critic_status == "passed"
    acceptance_state = "accepted" if success else "rejected"

    taste = profile.setdefault("user_taste_profile", {})
    judgment = profile.setdefault("product_judgment_profile", {})
    signals = profile.setdefault("acceptance_signals", [])
    _bucket_preference(taste, "quality_target_preferences", request.quality_target)
    _bucket_preference(taste, "task_family_preferences", request.task_family)

    if success:
        judgment["accepted_work_count"] = int(judgment.get("accepted_work_count", 0)) + 1
    else:
        judgment["rejected_work_count"] = int(judgment.get("rejected_work_count", 0)) + 1

    signals.append(
        {
            "signal_id": f"acceptance-{run.run_id}",
            "task_family": request.task_family,
            "quality_target": request.quality_target,
            "state": acceptance_state,
            "confidence": result.confidence,
            "critic_status": result.critic_status,
            "executor_id": run.selected_executor_id,
            "router_id": run.selected_router_id,
            "backend_ids": run.selected_backend_ids,
            "timestamp": utc_now(),
        }
    )
    profile["acceptance_signals"] = signals[-100:]
    save_payload(profile_path, profile)

    capability_prefs = portable.setdefault("capability_preferences", [])
    counts = {(item.get("capability_id"), item.get("preference_kind")): item for item in capability_prefs}
    preference_targets = [("executor", run.selected_executor_id), ("router", run.selected_router_id)]
    preference_targets.extend(("backend", backend_id) for backend_id in run.selected_backend_ids)
    for kind, capability_id in preference_targets:
        if not capability_id:
            continue
        row = counts.get((capability_id, kind))
        if row is None:
            row = {
                "capability_id": capability_id,
                "preference_kind": kind,
                "accepted_count": 0,
                "rejected_count": 0,
                "task_families": {},
                "confidence_sum": 0.0,
                "updated_at": utc_now(),
            }
            capability_prefs.append(row)
            counts[(capability_id, kind)] = row
        if success:
            row["accepted_count"] = int(row.get("accepted_count", 0)) + 1
        else:
            row["rejected_count"] = int(row.get("rejected_count", 0)) + 1
        task_families = row.setdefault("task_families", {})
        task_families[request.task_family] = int(task_families.get(request.task_family, 0)) + 1
        row["confidence_sum"] = round(float(row.get("confidence_sum", 0.0)) + float(result.confidence), 4)
        row["updated_at"] = utc_now()
    save_payload(portable_path, portable)


def update_product_context_from_discovery(root: Path, discovery: dict) -> None:
    ensure_state_files(root)
    context_path = root / "memory/product_context.yaml"
    payload = load_yaml_file(context_path)

    repo = discovery.get("repository", {})
    repo_files = list(iter_repo_files(root))
    modules = sorted(
        {
            path.relative_to(root).parts[0]
            for path in repo_files
            if path.relative_to(root).parts
            and not path.relative_to(root).parts[0].startswith(".")
            and path.relative_to(root).parts[0]
            not in {"capabilities", "memory", "orchestrator", "schemas", "scripts", "simulation", "telemetry", "training"}
        }
    )
    stack = repo.get("stacks", [])
    workflows = []
    if any("test" in str(path).lower() for path in repo_files):
        workflows.append("test")
    if (root / ".github/workflows").exists():
        workflows.append("ci")
    if any(path.suffix in {".tsx", ".jsx", ".html", ".css"} for path in repo_files):
        workflows.append("frontend")
    if any(path.name in {"Dockerfile", "docker-compose.yml", "docker-compose.yaml"} for path in repo_files):
        workflows.append("container")

    user_surfaces = sorted(
        {
            path.relative_to(root).parts[0]
            for path in repo_files
            if any(token in path.name.lower() for token in ("page", "view", "screen", "component", "route"))
        }
    )
    quality = payload.setdefault("product_quality_model", {})
    has_tests = workflows.count("test") > 0
    quality.update(
        {
            "architecture_quality": round(min(0.95, 0.45 + (0.1 * len(stack)) + (0.05 if has_tests else 0.0)), 2),
            "ux_quality": round(min(0.95, 0.45 + (0.08 if "frontend" in workflows else 0.0)), 2),
            "reliability": round(min(0.95, 0.45 + (0.08 if has_tests else 0.0) + (0.05 if "ci" in workflows else 0.0)), 2),
            "maintainability": round(min(0.95, 0.45 + (0.05 * min(len(modules), 4))), 2),
            "clarity": round(min(0.95, 0.5 + (0.05 if (root / "README.md").exists() else 0.0)), 2),
            "polish": round(min(0.95, 0.45 + (0.06 if "frontend" in workflows else 0.0)), 2),
            "distinctiveness": float(quality.get("distinctiveness", 0.5)),
            "last_refreshed_at": utc_now(),
        }
    )

    payload["product_intent_graph"] = {
        "repo_name": repo.get("name", root.name),
        "goal_summary": f"Continuously elevate `{repo.get('name', root.name)}` into a high-quality product.",
        "target_users": [],
        "feature_priorities": [],
        "differentiators": [],
        "constraints": [f"risk:{repo.get('risk_level', 'medium')}"],
        "last_refreshed_at": utc_now(),
    }
    payload["repo_ontology"] = {
        "repo_fingerprint": repo_fingerprint(root),
        "repo_name": repo.get("name", root.name),
        "stack": stack,
        "risk_level": repo.get("risk_level", "medium"),
        "file_count": repo.get("file_count", len(repo_files)),
        "modules": modules,
        "domains": stack,
        "workflows": workflows,
        "user_facing_surfaces": user_surfaces,
        "architecture_relationships": [f"module:{module}" for module in modules[:12]],
        "last_refreshed_at": utc_now(),
    }

    opportunities = []
    if not has_tests:
        opportunities.append(("reliability", "Add or expand automated tests and verification coverage.", 0.92))
    if not (root / "README.md").exists():
        opportunities.append(("clarity", "Add core product and repo documentation to improve clarity.", 0.85))
    if "frontend" in workflows and not user_surfaces:
        opportunities.append(("ux", "Map user-facing surfaces and tighten UX consistency.", 0.72))
    if "ci" not in workflows:
        opportunities.append(("consistency", "Add CI workflow checks for ongoing quality hardening.", 0.81))
    if not opportunities:
        opportunities.append(("polish", "Refine consistency, docs, and product details based on accepted work patterns.", 0.63))
    payload["opportunity_map"] = [
        {
            "opportunity_id": f"opportunity-{index+1}",
            "category": category,
            "summary": summary,
            "priority": index + 1,
            "confidence": confidence,
            "source": "bootstrap_discovery",
        }
        for index, (category, summary, confidence) in enumerate(opportunities)
    ]

    save_payload(context_path, payload)


def rebuild_portable_intelligence(root: Path, *, write: bool = True) -> dict:
    ensure_state_files(root)
    routes = load_yaml_file(root / "telemetry/routes.yaml")
    benchmarks = load_yaml_file(root / "capabilities/benchmarks.yaml")
    portable_path = root / "memory/portable_memory.yaml"
    profile_path = root / "memory/user_profile.yaml"
    payload = load_yaml_file(portable_path)
    profile = load_yaml_file(profile_path)

    verified_routes = [
        item
        for item in routes.get("routes", [])
        if not item.get("simulated", False) and (item.get("verified_execution") or item.get("critic_status") == "passed")
    ]
    all_real_routes = [item for item in routes.get("routes", []) if not item.get("simulated", False)]

    taste = profile.setdefault("user_taste_profile", {})
    judgment = profile.setdefault("product_judgment_profile", {})
    quality_pref_counter = Counter()
    task_family_counter = Counter()
    acceptance_signals = []
    for route in all_real_routes[-100:]:
        quality_target = route.get("quality_target")
        task_family = route.get("task_family")
        if quality_target:
            quality_pref_counter[quality_target] += 1
        if task_family:
            task_family_counter[task_family] += 1
        acceptance_signals.append(
            {
                "signal_id": f"rebuild-{route.get('run_id') or route.get('task_id')}",
                "task_family": task_family,
                "quality_target": quality_target,
                "state": "accepted" if route in verified_routes else "rejected",
                "confidence": float(route.get("confidence", 0.0)),
                "critic_status": route.get("critic_status"),
                "executor_id": route.get("executor_id"),
                "router_id": route.get("router_id"),
                "backend_ids": route.get("backend_ids", []),
                "timestamp": route.get("timestamp"),
            }
        )
    taste["quality_target_preferences"] = dict(quality_pref_counter)
    taste["task_family_preferences"] = dict(task_family_counter)
    judgment["accepted_work_count"] = len(verified_routes)
    judgment["rejected_work_count"] = max(0, len(all_real_routes) - len(verified_routes))
    profile["acceptance_signals"] = acceptance_signals[-100:]

    route_clusters = defaultdict(list)
    for item in verified_routes:
        key = (
            item.get("task_family"),
            item.get("quality_target"),
            item.get("executor_id"),
            item.get("router_id"),
            tuple(item.get("backend_ids", [])),
        )
        route_clusters[key].append(item)

    portable_route_preferences = []
    derived_lessons = []
    for index, ((task_family, quality_target, executor_id, router_id, backend_ids), items) in enumerate(sorted(route_clusters.items()), start=1):
        if not task_family:
            continue
        avg_confidence = round(sum(float(row.get("confidence", 0.0)) for row in items) / max(1, len(items)), 4)
        portable_route_preferences.append(
            {
                "preference_id": f"portable-route-{index}",
                "task_family": task_family,
                "repo_archetype": "generalized",
                "quality_target": quality_target,
                "preferred_executor_id": executor_id,
                "preferred_router_id": router_id,
                "preferred_backend_ids": list(backend_ids),
                "confidence": avg_confidence,
                "evidence_count": len(items),
                "updated_at": utc_now(),
            }
        )
        derived_lessons.append(
            {
                "lesson_id": f"portable-lesson-{index}",
                "task_family": task_family,
                "summary": f"For `{task_family}`, prefer `{executor_id}` with `{router_id}` and {len(backend_ids)} supporting backends when the quality target is `{quality_target}`.",
                "confidence": avg_confidence,
                "evidence_count": len(items),
                "source_type": "verified_routes",
                "updated_at": utc_now(),
            }
        )

    agent_metrics = benchmarks.get("agent_value_metrics", [])
    adapter_metrics = benchmarks.get("adapter_benchmarks", [])
    existing_preferences = payload.get("capability_preferences", [])
    preference_map = {(item.get("capability_id"), item.get("preference_kind")): item for item in existing_preferences}

    for agent in agent_metrics:
        cap_id = agent.get("agent_id")
        if not cap_id:
            continue
        row = preference_map.get((cap_id, "executor"))
        if row is None:
            row = {
                "capability_id": cap_id,
                "preference_kind": "executor",
                "accepted_count": 0,
                "rejected_count": 0,
                "task_families": {},
                "confidence_sum": 0.0,
                "updated_at": utc_now(),
            }
            existing_preferences.append(row)
            preference_map[(cap_id, "executor")] = row
        row["generalized_success_rate"] = round(
            float(agent.get("success_count", 0)) / max(1, int(agent.get("run_count", 0))),
            4,
        )
        row["updated_at"] = utc_now()

    for adapter in adapter_metrics:
        adapter_id = str(adapter.get("adapter_id", ""))
        match = re.match(r"backend:(.+?):", adapter_id)
        cap_id = match.group(1) if match else None
        if not cap_id:
            continue
        row = preference_map.get((cap_id, "backend"))
        if row is None:
            row = {
                "capability_id": cap_id,
                "preference_kind": "backend",
                "accepted_count": 0,
                "rejected_count": 0,
                "task_families": {},
                "confidence_sum": 0.0,
                "updated_at": utc_now(),
            }
            existing_preferences.append(row)
            preference_map[(cap_id, "backend")] = row
        row["generalized_success_rate"] = round(
            float(adapter.get("success_count", 0)) / max(1, int(adapter.get("run_count", 0))),
            4,
        )
        row["updated_at"] = utc_now()

    payload["portable_route_preferences"] = portable_route_preferences
    payload["derived_portable_lessons"] = derived_lessons
    payload["capability_preferences"] = existing_preferences
    payload["portable_memory"] = [
        {
            "record_id": "portable-memory-quality-bias",
            "classification": "portable",
            "type": "general_quality_pattern",
            "summary": "Balanced excellence with guarded high autonomy and meticulous refinement.",
            "confidence": 0.9,
            "updated_at": utc_now(),
        }
    ]
    if write:
        save_payload(portable_path, payload)
        save_payload(profile_path, profile)
    return {
        "summary": {
            "portable_route_preferences": len(portable_route_preferences),
            "derived_portable_lessons": len(derived_lessons),
            "capability_preferences": len(existing_preferences),
            "accepted_work_count": len(verified_routes),
        },
        "payload": payload,
    }


def build_transplant_payload(root: Path, target_root: Path) -> dict:
    ensure_state_files(root)
    user_profile = load_user_profile(root)
    rebuilt = rebuild_portable_intelligence(root, write=False)
    rebuild_summary = rebuilt["summary"]
    portable_memory = rebuilt["payload"]
    product_context = load_product_context(root)

    carried_sections = [
        "memory/user_profile.yaml:user_taste_profile",
        "memory/user_profile.yaml:product_judgment_profile",
        "memory/user_profile.yaml:autonomy_profile",
        "memory/portable_memory.yaml:portable_memory",
        "memory/portable_memory.yaml:derived_portable_lessons",
        "memory/portable_memory.yaml:portable_route_preferences",
        "memory/portable_memory.yaml:capability_preferences",
    ]
    stripped_sections = [
        "memory/facts.yaml",
        "memory/conflicts.yaml",
        "memory/product_context.yaml:repo_ontology",
        "telemetry/blackboard.yaml",
        "telemetry/control_plane.yaml",
        "telemetry/routes.yaml:routes",
        "capabilities/runtime.yaml",
        "telemetry/brain_network_installs.yaml:benchmarks",
    ]
    return {
        "payload_version": "1.0",
        "created_at": utc_now(),
        "source_repo": str(root.resolve()),
        "source_repo_fingerprint": repo_fingerprint(root),
        "target_repo": str(target_root.resolve()),
        "carried_sections": carried_sections,
        "stripped_sections": stripped_sections,
        "user_profiles": {
            "user_taste_profile": user_profile.get("user_taste_profile", {}),
            "product_judgment_profile": user_profile.get("product_judgment_profile", {}),
            "autonomy_profile": user_profile.get("autonomy_profile", {}),
        },
        "portable_memory": portable_memory.get("portable_memory", []),
        "derived_portable_lessons": portable_memory.get("derived_portable_lessons", []),
        "portable_route_preferences": portable_memory.get("portable_route_preferences", []),
        "capability_preferences": portable_memory.get("capability_preferences", []),
        "acceptance_signals": user_profile.get("acceptance_signals", [])[-25:],
        "source_product_context": {
            "product_intent_graph": product_context.get("product_intent_graph", {}),
            "product_quality_model": product_context.get("product_quality_model", {}),
        },
        "summary": rebuild_summary,
    }


def apply_transplant_payload(target_root: Path, payload: dict) -> None:
    ensure_state_files(target_root)
    user_profile_path = target_root / "memory/user_profile.yaml"
    portable_path = target_root / "memory/portable_memory.yaml"
    history_path = target_root / "telemetry/transplant_history.yaml"

    user_profile = load_yaml_file(user_profile_path)
    user_profile["user_taste_profile"] = payload.get("user_profiles", {}).get("user_taste_profile", {})
    user_profile["product_judgment_profile"] = payload.get("user_profiles", {}).get("product_judgment_profile", {})
    user_profile["autonomy_profile"] = payload.get("user_profiles", {}).get("autonomy_profile", {})
    user_profile["acceptance_signals"] = payload.get("acceptance_signals", [])
    save_payload(user_profile_path, user_profile)

    portable = load_yaml_file(portable_path)
    portable["portable_memory"] = payload.get("portable_memory", [])
    portable["derived_portable_lessons"] = payload.get("derived_portable_lessons", [])
    portable["portable_route_preferences"] = payload.get("portable_route_preferences", [])
    portable["capability_preferences"] = payload.get("capability_preferences", [])
    save_payload(portable_path, portable)

    history = load_yaml_file(history_path)
    transplants = history.setdefault("transplants", [])
    transplants.append(
        {
            "transplant_id": f"transplant-{hashlib.sha1(payload['created_at'].encode('utf-8')).hexdigest()[:12]}",
            "source_repo": payload.get("source_repo"),
            "source_repo_fingerprint": payload.get("source_repo_fingerprint"),
            "target_repo": payload.get("target_repo"),
            "created_at": payload.get("created_at"),
            "portable_payload_version": payload.get("payload_version", "1.0"),
            "carried_sections": payload.get("carried_sections", []),
            "stripped_sections": payload.get("stripped_sections", []),
            "imported_counts": {
                "portable_memory": len(payload.get("portable_memory", [])),
                "derived_portable_lessons": len(payload.get("derived_portable_lessons", [])),
                "portable_route_preferences": len(payload.get("portable_route_preferences", [])),
                "capability_preferences": len(payload.get("capability_preferences", [])),
            },
        }
    )
    save_payload(history_path, history)


def transplant_summary(root: Path) -> dict:
    ensure_state_files(root)
    portable = load_portable_memory(root)
    history = load_transplant_history(root)
    latest = sorted(history.get("transplants", []), key=lambda item: item.get("created_at", ""), reverse=True)[:1]
    return {
        "portable_memory_records": len(portable.get("portable_memory", [])),
        "derived_portable_lessons": len(portable.get("derived_portable_lessons", [])),
        "portable_route_preferences": len(portable.get("portable_route_preferences", [])),
        "capability_preferences": len(portable.get("capability_preferences", [])),
        "latest_transplant": latest[0] if latest else None,
    }
