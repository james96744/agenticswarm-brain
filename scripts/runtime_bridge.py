from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import re

try:
    from brain_utils import dump_json_stdout, dump_yaml_file, load_yaml_file, repo_root_from
except ModuleNotFoundError:
    from scripts.brain_utils import dump_json_stdout, dump_yaml_file, load_yaml_file, repo_root_from


RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
COMPLEXITY_ORDER = {"low": 0, "medium": 1, "high": 2}
SAFE_TOOL_CATEGORIES = {"search", "test", "data", "network", "mcp", "observability", "integration", "storage"}
PROVIDER_API_PROVIDERS = {"openai", "anthropic", "google", "azure_openai", "cohere", "mistral"}
LOCAL_RUNTIME_PROVIDERS = {"ollama", "vllm"}
PROVIDER_SECRET_REQUIREMENTS = {
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "azure_openai": ["AZURE_OPENAI_API_KEY"],
    "cohere": ["COHERE_API_KEY"],
    "mistral": ["MISTRAL_API_KEY"],
}
TASK_PROFILES = {
    "boilerplate_code": {
        "preferred_executor_ids": ["codex-cli", "aider-cli", "claude-cli"],
        "backend_categories": ["search", "test", "vcs"],
    },
    "data_migration": {
        "preferred_executor_ids": ["codex-cli", "claude-cli", "aider-cli"],
        "backend_categories": ["data", "search", "test", "vcs"],
    },
    "security_sensitive": {
        "preferred_executor_ids": ["claude-cli", "codex-cli"],
        "backend_categories": ["security", "mcp", "search", "data"],
    },
    "architecture_decision": {
        "preferred_executor_ids": ["claude-cli", "codex-cli"],
        "backend_categories": ["mcp", "search"],
    },
    "default": {
        "preferred_executor_ids": ["codex-cli", "claude-cli", "python-workflow-runner"],
        "backend_categories": ["search", "data"],
    },
}
KNOWN_EXECUTORS = {
    "codex": {
        "executor_id": "codex-cli",
        "kind": "agent_cli",
        "supports_code": True,
        "supports_tools": True,
        "supports_streaming": True,
        "supported_task_families": [
            "coding",
            "refactor",
            "integration",
            "debugging",
            "review",
            "boilerplate_code",
            "data_migration",
        ],
        "strengths": ["repo_aware_execution", "tool_use", "code_changes"],
    },
    "claude": {
        "executor_id": "claude-cli",
        "kind": "agent_cli",
        "supports_code": True,
        "supports_tools": True,
        "supports_streaming": True,
        "supported_task_families": [
            "research",
            "review",
            "architecture",
            "architecture_decision",
            "security_sensitive",
        ],
        "strengths": ["analysis", "architecture", "high_context"],
    },
    "aider": {
        "executor_id": "aider-cli",
        "kind": "agent_cli",
        "supports_code": True,
        "supports_tools": True,
        "supports_streaming": True,
        "supported_task_families": [
            "coding",
            "refactor",
            "debugging",
            "integration",
            "boilerplate_code",
        ],
        "strengths": ["file_editing", "git_patching"],
    },
}


def normalize_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "unknown"


def now_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def base_command(value: str | None) -> str:
    if not value:
        return ""
    return Path(str(value).split()[0]).name


def dedupe(items: list[dict], key: str) -> list[dict]:
    seen: dict[str, dict] = {}
    for item in items:
        seen[str(item[key])] = item
    return list(seen.values())


def load_runtime_inputs(root: Path) -> dict:
    return {
        "agents": load_yaml_file(root / "capabilities/agents.yaml"),
        "models": load_yaml_file(root / "capabilities/models.yaml"),
        "plugins": load_yaml_file(root / "capabilities/plugins.yaml"),
        "mcp": load_yaml_file(root / "capabilities/mcp.yaml"),
        "cli": load_yaml_file(root / "capabilities/cli.yaml"),
        "benchmarks": load_yaml_file(root / "capabilities/benchmarks.yaml"),
        "routes": load_yaml_file(root / "telemetry/routes.yaml"),
        "runtime": load_yaml_file(root / "capabilities/runtime.yaml"),
    }


def discover_agent_executors(cli_entries: list[dict]) -> list[dict]:
    results = []
    has_python = False

    for cli in cli_entries:
        command = base_command(cli.get("command"))
        cli_id = cli.get("cli_id", "")
        if command in {"python", "python3"} or cli_id in {"python", "python3"}:
            has_python = True

        known = KNOWN_EXECUTORS.get(command) or KNOWN_EXECUTORS.get(cli_id)
        if not known:
            continue

        results.append(
            {
                "executor_id": known["executor_id"],
                "enabled": bool(cli.get("enabled", True)),
                "kind": known["kind"],
                "command": cli.get("command", command),
                "path": cli.get("path"),
                "runtime": cli.get("runtime", "unknown"),
                "scope": cli.get("scope", "global"),
                "source": f"cli:{cli.get('source', 'unknown')}",
                "supports_code": known["supports_code"],
                "supports_tools": known["supports_tools"],
                "supports_streaming": known["supports_streaming"],
                "supports_direct_invocation": True,
                "invocation_mode": "raw_command",
                "supported_task_families": known["supported_task_families"],
                "strengths": known["strengths"],
                "auth_required": False,
                "secret_requirements": [],
                "health_status": "ready",
            }
        )

    if has_python:
        results.append(
            {
                "executor_id": "python-workflow-runner",
                "enabled": True,
                "kind": "workflow_runner",
                "command": "python3",
                "path": None,
                "runtime": "python",
                "scope": "global",
                "source": "cli:path_lookup",
                "supports_code": False,
                "supports_tools": True,
                "supports_streaming": False,
                "supports_direct_invocation": True,
                "invocation_mode": "raw_command",
                "supported_task_families": ["discovery", "validation", "maintenance", "simulation"],
                "strengths": ["local_script_execution", "maintenance"],
                "auth_required": False,
                "secret_requirements": [],
                "health_status": "ready",
            }
        )

    results.append(
        {
            "executor_id": "remote-worker",
            "enabled": True,
            "kind": "remote_worker",
            "command": None,
            "path": None,
            "runtime": "queued_dispatch",
            "scope": "global",
            "source": "runtime_template",
            "supports_code": True,
            "supports_tools": True,
            "supports_streaming": False,
            "supports_direct_invocation": False,
            "invocation_mode": "queued_dispatch",
            "supported_task_families": ["coding", "research", "review", "security_sensitive", "architecture_decision", "data_migration"],
            "strengths": ["deferred_execution", "remote_capacity", "queue_dispatch"],
            "auth_required": False,
            "secret_requirements": [],
            "health_status": "ready",
        }
    )

    return dedupe(results, "executor_id")


def router_kind_for_provider(provider: str) -> str:
    if provider in PROVIDER_API_PROVIDERS:
        return "provider_api"
    if provider in LOCAL_RUNTIME_PROVIDERS:
        return "local_runtime"
    return "catalog_router"


def router_tier_coverage(provider: str, models: list[dict]) -> list[str]:
    actual = sorted({model.get("tier") for model in models if model.get("tier")})
    if provider in PROVIDER_API_PROVIDERS:
        return ["tier_0_router", "tier_1_worker", "tier_2_critic", "tier_3_expert"]
    if provider in LOCAL_RUNTIME_PROVIDERS:
        merged = set(actual)
        merged.update({"tier_0_router", "tier_1_worker", "tier_2_critic"})
        return sorted(merged)
    return actual


def discover_model_routers(models: list[dict]) -> list[dict]:
    by_provider: dict[str, list[dict]] = {}
    for model in models:
        provider = model.get("provider")
        if not provider:
            continue
        by_provider.setdefault(provider, []).append(model)

    results = []
    for provider, provider_models in sorted(by_provider.items()):
        kind = router_kind_for_provider(provider)
        statuses = {item.get("status") for item in provider_models}
        health_status = "ready" if "available" in statuses or provider in PROVIDER_API_PROVIDERS else "catalog_only"
        results.append(
            {
                "router_id": f"{normalize_id(provider)}-router",
                "enabled": True,
                "kind": kind,
                "provider": provider,
                "scope": provider_models[0].get("scope", "global"),
                "source": "runtime_registry",
                "available_model_ids": sorted(model.get("model_id") for model in provider_models if model.get("model_id")),
                "tier_coverage": router_tier_coverage(provider, provider_models),
                "supports_dynamic_tiering": kind in {"provider_api", "local_runtime"},
                "selection_strategy": "tier_then_task_family",
                "auth_required": provider in PROVIDER_API_PROVIDERS,
                "secret_requirements": PROVIDER_SECRET_REQUIREMENTS.get(provider, []),
                "health_status": health_status,
            }
        )

    return dedupe(results, "router_id")


def backend_category_for_mcp(entry: dict) -> str:
    joined = " ".join(str(entry.get(key, "")) for key in ("mcp_id", "command", "url", "path")).lower()
    if "semgrep" in joined or "security" in joined:
        return "security"
    return "mcp"


def discover_tool_backends(mcp_entries: list[dict], plugins: list[dict], cli_entries: list[dict]) -> list[dict]:
    results = []

    for entry in mcp_entries:
        backend_kind = "mcp_server" if entry.get("kind") == "server_definition" else "mcp_config"
        if entry.get("transport") == "http" and entry.get("url"):
            backend_kind = "http_api"
        results.append(
            {
                "backend_id": f"mcp-{entry.get('mcp_id')}",
                "enabled": bool(entry.get("enabled", True)),
                "kind": backend_kind,
                "category": backend_category_for_mcp(entry),
                "scope": entry.get("scope", "global"),
                "source": f"mcp:{entry.get('source', 'unknown')}",
                "path": entry.get("path"),
                "transport": entry.get("transport"),
                "command": entry.get("command"),
                "url": entry.get("url"),
                "capabilities": entry.get("capabilities", []),
                "destructive": False,
                "auth_required": bool(entry.get("auth_required", False)) or bool(entry.get("url")),
                "secret_requirements": entry.get("secret_requirements", []),
                "destructive_capabilities": [],
                "supports_direct_invocation": entry.get("kind") == "server_definition" and bool(entry.get("command") or entry.get("url")),
                "health_status": (
                    "ready"
                    if entry.get("kind") == "server_definition" and entry.get("enabled", True)
                    else "configured"
                    if entry.get("enabled", True)
                    else "disabled"
                ),
            }
        )

    for plugin in plugins:
        results.append(
            {
                "backend_id": f"plugin-{plugin.get('plugin_id')}",
                "enabled": bool(plugin.get("enabled", True)),
                "kind": "plugin",
                "category": plugin.get("category", "integration"),
                "scope": plugin.get("scope", "global"),
                "source": f"plugin:{plugin.get('source', 'unknown')}",
                "path": plugin.get("path"),
                "capabilities": plugin.get("capabilities", []),
                "destructive": bool(plugin.get("destructive_capabilities")),
                "auth_required": plugin.get("auth_required", "depends") not in {False, "false"},
                "secret_requirements": plugin.get("secret_requirements", []),
                "destructive_capabilities": plugin.get("destructive_capabilities", []),
                "supports_direct_invocation": True,
                "health_status": "ready" if plugin.get("enabled", True) else "disabled",
            }
        )

    for cli in cli_entries:
        category = cli.get("category", "general")
        if category not in SAFE_TOOL_CATEGORIES and category not in {"vcs", "security"}:
            continue
        results.append(
            {
                "backend_id": f"cli-{cli.get('cli_id')}",
                "enabled": bool(cli.get("enabled", True)),
                "kind": "cli",
                "category": category,
                "scope": cli.get("scope", "global"),
                "source": f"cli:{cli.get('source', 'unknown')}",
                "path": cli.get("path"),
                "command": cli.get("command"),
                "capabilities": [category],
                "destructive": bool(cli.get("destructive", False)),
                "supports_json_output": bool(cli.get("supports_json_output", False)),
                "auth_required": False,
                "secret_requirements": [],
                "destructive_capabilities": [category] if cli.get("destructive", False) else [],
                "supports_direct_invocation": True,
                "health_status": "ready" if cli.get("enabled", True) else "disabled",
            }
        )

    return dedupe(results, "backend_id")


def observed_success_maps(benchmarks_payload: dict, routes_payload: dict) -> dict:
    executor_rates: dict[tuple[str, str], float] = {}
    router_rates: dict[tuple[str, str], float] = {}
    backend_rates: dict[tuple[str, str], float] = {}
    executor_counts = defaultdict(lambda: {"success": 0, "total": 0})
    router_counts = defaultdict(lambda: {"success": 0, "total": 0})
    backend_counts = defaultdict(lambda: {"success": 0, "total": 0})

    for route in routes_payload.get("routes", []):
        if route.get("simulated", False):
            continue
        task_family = route.get("task_family")
        replay_score = float(route.get("replay_score", 0.0))
        successful = route.get("status") == "success" and route.get("critic_status") == "passed"
        executor_id = route.get("executor_id")
        router_id = route.get("router_id")
        if task_family and executor_id:
            key = (task_family, executor_id)
            executor_counts[key]["total"] += 1
            executor_counts[key]["success"] += replay_score if replay_score else (1 if successful else 0)
        if task_family and router_id:
            key = (task_family, router_id)
            router_counts[key]["total"] += 1
            router_counts[key]["success"] += replay_score if replay_score else (1 if successful else 0)
        for backend_id in route.get("backend_ids", []):
            key = (task_family, backend_id)
            backend_counts[key]["total"] += 1
            backend_counts[key]["success"] += replay_score if replay_score else (1 if successful else 0)

    for key, counts in executor_counts.items():
        executor_rates[key] = counts["success"] / max(1, counts["total"])
    for key, counts in router_counts.items():
        router_rates[key] = counts["success"] / max(1, counts["total"])
    for key, counts in backend_counts.items():
        backend_rates[key] = counts["success"] / max(1, counts["total"])

    for item in benchmarks_payload.get("agent_value_metrics", []):
        task_family = item.get("task_family")
        agent_id = item.get("agent_id")
        if task_family and agent_id and item.get("run_count", 0):
            executor_rates[(task_family, agent_id)] = max(
                executor_rates.get((task_family, agent_id), 0.0),
                float(item.get("success_count", 0)) / max(1, int(item.get("run_count", 0))),
            )
    for item in benchmarks_payload.get("model_benchmarks", []):
        task_family = item.get("task_family")
        model_id = item.get("model_id")
        if task_family and model_id and item.get("run_count", 0):
            router_rates[(task_family, model_id)] = max(
                router_rates.get((task_family, model_id), 0.0),
                float(item.get("success_count", 0)) / max(1, int(item.get("run_count", 0))),
            )

    for preference in routes_payload.get("route_preferences", []):
        task_family = preference.get("task_family")
        pref_score = float(preference.get("avg_replay_score", 0.0))
        executor_id = preference.get("executor_id")
        router_id = preference.get("router_id")
        if task_family and executor_id:
            executor_rates[(task_family, executor_id)] = max(
                executor_rates.get((task_family, executor_id), 0.0),
                pref_score,
            )
        if task_family and router_id:
            router_rates[(task_family, router_id)] = max(
                router_rates.get((task_family, router_id), 0.0),
                pref_score,
            )
        for backend_id in preference.get("backend_ids", []):
            backend_rates[(task_family, backend_id)] = max(
                backend_rates.get((task_family, backend_id), 0.0),
                pref_score,
            )

    replay_ready = sorted(
        [
            route for route in routes_payload.get("routes", [])
            if not route.get("simulated", False) and route.get("replay_eligible")
        ]
        + [
            {
                "task_family": item.get("task_family"),
                "run_id": item.get("last_run_id"),
                "executor_id": item.get("executor_id"),
                "router_id": item.get("router_id"),
                "backend_ids": item.get("backend_ids", []),
                "replay_score": item.get("avg_replay_score", 0.0),
            }
            for item in routes_payload.get("route_preferences", [])
            if float(item.get("avg_replay_score", 0.0)) >= 0.7 and float(item.get("success_rate", 0.0)) >= 0.75
        ],
        key=lambda item: float(item.get("replay_score", 0.0)),
        reverse=True,
    )

    return {
        "executor_rates": executor_rates,
        "router_rates": router_rates,
        "backend_rates": backend_rates,
        "replay_ready": replay_ready,
    }


def build_runtime_registry(root: Path, *, write: bool) -> dict:
    inputs = load_runtime_inputs(root)
    runtime = inputs["runtime"]
    runtime["agent_executors"] = discover_agent_executors(inputs["cli"].get("cli_entries", []))
    runtime["model_routers"] = discover_model_routers(inputs["models"].get("models", []))
    runtime["tool_backends"] = discover_tool_backends(
        inputs["mcp"].get("mcp_entries", []),
        inputs["plugins"].get("plugins", []),
        inputs["cli"].get("cli_entries", []),
    )
    runtime["last_updated"] = now_date()
    if write:
        dump_yaml_file(root / "capabilities/runtime.yaml", runtime)
    return runtime


def task_profile(task_family: str) -> dict:
    return TASK_PROFILES.get(task_family, TASK_PROFILES["default"])


def build_tier_path(task: dict, policies: dict) -> list[str]:
    route = []
    if policies.get("routing_policy", {}).get("semantic_router_enabled", False):
        route.append("tier_0_router")
    route.append("tier_1_worker")

    risk = RISK_ORDER.get(task.get("risk_level", "medium"), 1)
    complexity = COMPLEXITY_ORDER.get(task.get("complexity", "medium"), 1)
    critic_needed = task.get("requires_code", False) or task.get("requires_tools", False) or risk >= 1
    if critic_needed:
        route.append("tier_2_critic")

    expert_needed = task.get("force_expert", False) or task.get("high_stakes", False) or risk >= 2 or complexity >= 2
    if expert_needed:
        route.append("tier_3_expert")

    return route


def select_executor(executors: list[dict], task: dict, observed: dict) -> tuple[dict | None, float]:
    profile = task_profile(task.get("task_family", "default"))
    best = None
    best_score = -1.0
    for executor in executors:
        if not executor.get("enabled", True) or executor.get("health_status") != "ready":
            continue
        score = 0.35
        if task.get("dispatch_mode") == "remote_worker":
            score += 0.5 if executor.get("executor_id") == "remote-worker" else -0.25
        if executor.get("executor_id") in profile["preferred_executor_ids"]:
            score += 0.3
        if task.get("requires_code", False):
            score += 0.25 if executor.get("supports_code") else -0.3
        if task.get("requires_tools", False):
            score += 0.15 if executor.get("supports_tools") else -0.2
        if task.get("task_family") in executor.get("supported_task_families", []):
            score += 0.15
        if executor.get("scope") == "local":
            score += 0.05
        if task.get("high_stakes", False) and "architecture" in executor.get("strengths", []):
            score += 0.05
        score += 0.2 * observed["executor_rates"].get((task.get("task_family"), executor.get("executor_id")), 0.0)
        if score > best_score:
            best = executor
            best_score = score
    return best, round(max(best_score, 0.0), 2)


def select_router(routers: list[dict], task: dict, observed: dict) -> tuple[dict | None, float]:
    best = None
    best_score = -1.0
    for router in routers:
        if not router.get("enabled", True):
            continue
        score = 0.35
        if router.get("health_status") == "ready":
            score += 0.3
        elif router.get("health_status") == "catalog_only":
            score += 0.1
        if router.get("supports_dynamic_tiering", False):
            score += 0.15
        if task.get("quality_target") in {"deep", "critical"} and "tier_3_expert" in router.get("tier_coverage", []):
            score += 0.1
        if task.get("risk_level") == "low" and router.get("kind") == "local_runtime":
            score += 0.05
        score += 0.15 * observed["router_rates"].get((task.get("task_family"), router.get("router_id")), 0.0)
        if score > best_score:
            best = router
            best_score = score
    return best, round(max(best_score, 0.0), 2)


def model_candidates_for_tier(models_payload: dict, tier: str, provider: str | None) -> list[dict]:
    models = models_payload.get("models", [])
    candidates = [model for model in models if model.get("enabled", True) and model.get("tier") == tier]
    if provider:
        filtered = [model for model in candidates if model.get("provider") == provider]
        return filtered
    return candidates


def select_models_for_route(models_payload: dict, router: dict | None, tier_path: list[str]) -> dict[str, dict]:
    assignments: dict[str, dict] = {}
    provider = router.get("provider") if router else None
    templates = models_payload.get("model_templates", [])

    for tier in tier_path:
        candidates = model_candidates_for_tier(models_payload, tier, provider)
        if candidates:
            model = candidates[0]
            assignments[tier] = {
                "model_id": model.get("model_id"),
                "provider": model.get("provider"),
                "source": model.get("source", "registry"),
                "status": model.get("status"),
            }
            continue

        if router and router.get("kind") == "provider_api" and router.get("health_status") == "ready":
            assignments[tier] = {
                "model_id": f"{router.get('provider')}:auto:{tier}",
                "provider": router.get("provider"),
                "source": "provider_dynamic",
                "status": "inferred",
            }
            continue

        template = next((item for item in templates if item.get("tier") == tier), None)
        assignments[tier] = {
            "model_id": template.get("model_id") if template else f"{tier}-unassigned",
            "provider": template.get("provider") if template else "unassigned",
            "source": "template_fallback" if template else "missing",
            "status": template.get("status", "template") if template else "missing",
        }

    return assignments


def backend_score(backend: dict, desired_category: str, task: dict, observed: dict) -> float:
    score = 0.25
    if backend.get("health_status") == "ready":
        score += 0.15
    if backend.get("category") == desired_category:
        score += 0.35
    if desired_category == "mcp" and backend.get("kind", "").startswith("mcp"):
        score += 0.25
    if backend.get("kind") == "mcp_server":
        score += 0.1
    if backend.get("kind") == "http_api":
        score += 0.12
    if backend.get("kind") == "mcp_config":
        score -= 0.05
    if desired_category == "security" and "security" in " ".join(map(str, backend.get("capabilities", []))).lower():
        score += 0.35
    if desired_category == "security" and "semgrep" in backend.get("backend_id", ""):
        score += 0.35
    if backend.get("scope") == "local":
        score += 0.05
    if not backend.get("destructive", False):
        score += 0.05
    if task.get("requires_code", False) and backend.get("category") in {"search", "test", "vcs"}:
        score += 0.05
    score += 0.15 * observed["backend_rates"].get((task.get("task_family"), backend.get("backend_id")), 0.0)
    return score


def select_backends(backends: list[dict], task: dict, limit: int, observed: dict) -> list[dict]:
    if not task.get("requires_tools", False) and not task.get("requires_code", False):
        return []

    profile = task_profile(task.get("task_family", "default"))
    selected: list[dict] = []
    used_ids: set[str] = set()

    for desired_category in profile["backend_categories"]:
        ranked = sorted(backends, key=lambda item: backend_score(item, desired_category, task, observed), reverse=True)
        for candidate in ranked:
            if not candidate.get("enabled", True):
                continue
            if candidate.get("backend_id") in used_ids:
                continue
            if backend_score(candidate, desired_category, task, observed) < 0.45:
                continue
            selected.append(candidate)
            used_ids.add(candidate["backend_id"])
            break
        if len(selected) >= limit:
            break

    if task.get("requires_tools", False) and not any(item.get("kind", "").startswith("mcp") for item in selected):
        ranked_mcp = sorted(backends, key=lambda item: backend_score(item, "mcp", task, observed), reverse=True)
        for candidate in ranked_mcp:
            if candidate.get("backend_id") in used_ids or not candidate.get("enabled", True):
                continue
            if candidate.get("kind", "").startswith("mcp"):
                selected.append(candidate)
                used_ids.add(candidate["backend_id"])
                break

    return selected[:limit]


def plan_execution(root: Path, task: dict, *, runtime_registry: dict | None = None, policies: dict | None = None) -> dict:
    runtime_registry = runtime_registry or load_yaml_file(root / "capabilities/runtime.yaml")
    policies = policies or load_yaml_file(root / "orchestrator/policies.yaml")
    models_payload = load_yaml_file(root / "capabilities/models.yaml")
    benchmarks_payload = load_yaml_file(root / "capabilities/benchmarks.yaml")
    routes_payload = load_yaml_file(root / "telemetry/routes.yaml")
    observed = observed_success_maps(benchmarks_payload, routes_payload)

    tier_path = build_tier_path(task, policies)
    executor, executor_score = select_executor(runtime_registry.get("agent_executors", []), task, observed)
    router, router_score = select_router(runtime_registry.get("model_routers", []), task, observed)
    backends = select_backends(
        runtime_registry.get("tool_backends", []),
        task,
        runtime_registry.get("selection_policy", {}).get("limit_default_backend_bundle", 4),
        observed,
    )
    assignments = select_models_for_route(models_payload, router, tier_path)

    reasons = []
    if executor:
        reasons.append(f"executor:{executor['executor_id']}")
    else:
        reasons.append("executor:missing")
    if router:
        reasons.append(f"router:{router['router_id']}")
    else:
        reasons.append("router:missing")
    if backends:
        reasons.append(f"backends:{','.join(item['backend_id'] for item in backends)}")
    replay = next((route for route in observed["replay_ready"] if route.get("task_family") == task.get("task_family")), None)
    if replay:
        reasons.append(f"replay_candidate:{replay.get('run_id')}")

    confidence = round(min(1.0, 0.45 + executor_score * 0.25 + router_score * 0.2 + len(backends) * 0.03), 2)
    unresolved = []
    if executor is None:
        unresolved.append("missing_executor")
    if router is None:
        unresolved.append("missing_router")

    return {
        "task_family": task.get("task_family", "unknown"),
        "quality_target": task.get("quality_target", "balanced"),
        "risk_level": task.get("risk_level", "medium"),
        "dispatch_mode": task.get("dispatch_mode", "immediate"),
        "requires_code": bool(task.get("requires_code", False)),
        "requires_tools": bool(task.get("requires_tools", False)),
        "model_tier_path": tier_path,
        "selected_executor": executor,
        "selected_router": router,
        "model_assignments": assignments,
        "backend_bundle": backends,
        "confidence": confidence,
        "reasons": reasons,
        "replay_candidate": replay,
        "unresolved": unresolved,
        "planned_at": datetime.now(timezone.utc).isoformat(),
    }


def scenario_tasks(root: Path, scenario_id: str | None = None) -> list[dict]:
    scenarios = load_yaml_file(root / "simulation/scenarios.yaml").get("scenarios", [])
    if scenario_id is None:
        return scenarios
    return [scenario for scenario in scenarios if scenario.get("scenario_id") == scenario_id]


def runtime_summary(runtime_registry: dict) -> dict:
    return {
        "executors": len(runtime_registry.get("agent_executors", [])),
        "routers": len(runtime_registry.get("model_routers", [])),
        "backends": len(runtime_registry.get("tool_backends", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build runtime capability bridges and dry-run execution planning.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sync-only", action="store_true")
    parser.add_argument("--from-scenarios", action="store_true")
    parser.add_argument("--scenario-id", default=None)
    parser.add_argument("--task-family", default=None)
    parser.add_argument("--complexity", default="medium")
    parser.add_argument("--risk-level", default="medium")
    parser.add_argument("--quality-target", default="balanced")
    parser.add_argument("--dispatch-mode", default="immediate")
    parser.add_argument("--requires-code", action="store_true")
    parser.add_argument("--requires-tools", action="store_true")
    parser.add_argument("--high-stakes", action="store_true")
    parser.add_argument("--force-expert", action="store_true")
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    runtime_registry = build_runtime_registry(root, write=not args.dry_run)
    policies = load_yaml_file(root / "orchestrator/policies.yaml")

    tasks = []
    if args.task_family:
        tasks.append(
            {
                "task_family": args.task_family,
                "complexity": args.complexity,
                "risk_level": args.risk_level,
                "quality_target": args.quality_target,
                "dispatch_mode": args.dispatch_mode,
                "requires_code": args.requires_code,
                "requires_tools": args.requires_tools,
                "high_stakes": args.high_stakes,
                "force_expert": args.force_expert,
            }
        )
    elif args.sync_only:
        tasks = []
    else:
        tasks = scenario_tasks(root, args.scenario_id if args.from_scenarios or args.scenario_id else None)

    plans = [plan_execution(root, task, runtime_registry=runtime_registry, policies=policies) for task in tasks]
    payload = {
        "runtime_summary": runtime_summary(runtime_registry),
        "plans": plans,
    }
    dump_json_stdout(payload)

    unresolved = any(plan.get("unresolved") for plan in plans)
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
