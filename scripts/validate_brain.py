from __future__ import annotations

import argparse
from pathlib import Path

try:
    from brain_utils import load_json_file, load_yaml_file, repo_root_from
except ModuleNotFoundError:
    from scripts.brain_utils import load_json_file, load_yaml_file, repo_root_from


FILE_SCHEMA_MAP = {
    "brain.schema.yaml": "schemas/brain_manifest.schema.json",
    "capabilities/agents.yaml": "schemas/capabilities/agents.schema.json",
    "capabilities/benchmarks.yaml": "schemas/capabilities/benchmarks.schema.json",
    "capabilities/cli.yaml": "schemas/capabilities/cli.schema.json",
    "capabilities/mcp.yaml": "schemas/capabilities/mcp.schema.json",
    "capabilities/models.yaml": "schemas/capabilities/models.schema.json",
    "capabilities/plugins.yaml": "schemas/capabilities/plugins.schema.json",
    "capabilities/runtime.yaml": "schemas/capabilities/runtime.schema.json",
    "capabilities/skills.yaml": "schemas/capabilities/skills.schema.json",
    "memory/conflicts.yaml": "schemas/memory/conflicts.schema.json",
    "memory/facts.yaml": "schemas/memory/facts.schema.json",
    "orchestrator/autopilot.yaml": "schemas/orchestrator/autopilot.schema.json",
    "orchestrator/anatomy_registry.yaml": "schemas/orchestrator/anatomy_registry.schema.json",
    "orchestrator/policies.yaml": "schemas/orchestrator/policies.schema.json",
    "simulation/scenarios.yaml": "schemas/simulation/scenarios.schema.json",
    "telemetry/audit_report.yaml": "schemas/telemetry/audit_report.schema.json",
    "telemetry/autopilot_state.yaml": "schemas/telemetry/autopilot_state.schema.json",
    "telemetry/blackboard.yaml": "schemas/telemetry/blackboard.schema.json",
    "telemetry/control_plane.yaml": "schemas/telemetry/control_plane.schema.json",
    "telemetry/discovery_state.yaml": "schemas/telemetry/discovery_state.schema.json",
    "telemetry/routes.yaml": "schemas/telemetry/routes.schema.json",
    "training/adapters.yaml": "schemas/training/adapters.schema.json",
    "training/jobs.yaml": "schemas/training/jobs.schema.json",
}

DISCOVERED_PATH_CHECKS = (
    ("capabilities/agents.yaml", "agents", "agent_id"),
    ("capabilities/skills.yaml", "skills", "skill_id"),
    ("capabilities/plugins.yaml", "plugins", "plugin_id"),
    ("capabilities/mcp.yaml", "mcp_entries", "mcp_id"),
    ("capabilities/cli.yaml", "cli_entries", "cli_id"),
)

MODEL_TIERS = {"tier_0_router", "tier_1_worker", "tier_2_critic", "tier_3_expert"}
ANATOMY_KEYS = {"cerebrum", "cerebellum", "limbic_system", "neurons", "dendrites", "brainstem"}
PACKAGING_TIERS = {"community", "advanced", "enterprise"}


def require_jsonschema():
    try:
        import jsonschema  # type: ignore
    except ImportError:  # pragma: no cover - dependency gate
        print(
            "jsonschema is required. Install with `pip install jsonschema pyyaml`.",
            file=__import__("sys").stderr,
        )
        raise SystemExit(2)
    return jsonschema


def validate_file(root: Path, yaml_path: Path, schema_path: Path) -> list[str]:
    errors = []
    jsonschema = require_jsonschema()
    schema = load_json_file(schema_path)
    payload = load_yaml_file(yaml_path)
    validator = jsonschema.Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(payload), key=str):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{yaml_path.relative_to(root)}:{location}: {error.message}")
    return errors


def add_duplicate_errors(errors: list[str], label: str, items: list[dict], key: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in items:
        value = item.get(key)
        if not value:
            continue
        if value in seen:
            duplicates.add(str(value))
        seen.add(str(value))
    for duplicate in sorted(duplicates):
        errors.append(f"{label}: duplicate {key} `{duplicate}`")


def add_missing_local_path_errors(root: Path, errors: list[str], label: str, items: list[dict], key: str) -> None:
    for item in items:
        if item.get("scope") != "local":
            continue
        path_value = item.get("path")
        if not path_value:
            errors.append(f"{label}: local entry `{item.get(key, 'unknown')}` is missing `path`")
            continue
        if not (root / path_value).exists():
            errors.append(f"{label}: local entry `{item.get(key, 'unknown')}` points to missing path `{path_value}`")


def semantic_checks(root: Path) -> list[str]:
    errors = []
    brain_data = load_yaml_file(root / "brain.schema.yaml")
    brain = brain_data.get("brain_manifest", {})
    anatomy_registry_ref = brain.get("anatomy_registry", {}).get("path", "orchestrator/anatomy_registry.yaml")
    anatomy_registry = load_yaml_file(root / anatomy_registry_ref)
    policies = load_yaml_file(root / "orchestrator/policies.yaml")

    brain_anatomy = set(brain.get("anatomy_map", {}).keys())
    policy_anatomy = set(policies.get("anatomy_policy", {}).keys()) & ANATOMY_KEYS
    registry_anatomy = set(anatomy_registry.get("anatomy_modules", {}).keys())
    if brain_anatomy and brain_anatomy != ANATOMY_KEYS:
        errors.append("brain.schema.yaml:anatomy_map must define cerebrum, cerebellum, limbic_system, neurons, dendrites, and brainstem")
    if policy_anatomy and policy_anatomy != ANATOMY_KEYS:
        errors.append("orchestrator/policies.yaml:anatomy_policy must define cerebrum, cerebellum, limbic_system, neurons, dendrites, and brainstem")
    if registry_anatomy and registry_anatomy != ANATOMY_KEYS:
        errors.append("orchestrator/anatomy_registry.yaml:anatomy_modules must define cerebrum, cerebellum, limbic_system, neurons, dendrites, and brainstem")
    if brain_anatomy and policy_anatomy and brain_anatomy != policy_anatomy:
        errors.append("brain.schema.yaml:anatomy_map must match orchestrator/policies.yaml anatomy_policy core anatomy keys")
    if brain_anatomy and registry_anatomy and brain_anatomy != registry_anatomy:
        errors.append("brain.schema.yaml:anatomy_map must match orchestrator/anatomy_registry.yaml anatomy_modules keys")

    wrapper_entrypoints = brain.get("anatomy_registry", {}).get("wrapper_entrypoints", {})
    for anatomy_key, wrapper_path in wrapper_entrypoints.items():
        if anatomy_key not in ANATOMY_KEYS:
            errors.append(f"brain.schema.yaml:anatomy_registry.wrapper_entrypoints includes unsupported anatomy key `{anatomy_key}`")
            continue
        if not (root / wrapper_path).exists():
            errors.append(f"brain.schema.yaml:anatomy_registry.wrapper_entrypoints.{anatomy_key} points to missing file `{wrapper_path}`")

    for anatomy_key, module in anatomy_registry.get("anatomy_modules", {}).items():
        wrapper_path = module.get("wrapper_entrypoint")
        if wrapper_path and not (root / wrapper_path).exists():
            errors.append(f"orchestrator/anatomy_registry.yaml:{anatomy_key}.wrapper_entrypoint points to missing file `{wrapper_path}`")
        if wrapper_entrypoints.get(anatomy_key) and wrapper_entrypoints.get(anatomy_key) != wrapper_path:
            errors.append(
                f"brain.schema.yaml:anatomy_registry.wrapper_entrypoints.{anatomy_key} must match orchestrator/anatomy_registry.yaml wrapper_entrypoint"
            )
        for ref in module.get("module_refs", []):
            path_value = ref.get("path")
            if path_value and not (root / path_value).exists():
                errors.append(f"orchestrator/anatomy_registry.yaml:{anatomy_key}.module_refs points to missing path `{path_value}`")
        for action, action_config in module.get("actions", {}).items():
            target = action_config.get("target")
            if target and not (root / target).exists():
                errors.append(f"orchestrator/anatomy_registry.yaml:{anatomy_key}.actions.{action}.target points to missing file `{target}`")

    brain_critic = set(brain.get("policies", {}).get("require_critic_for", []))
    policy_critic = set(policies.get("verification_policy", {}).get("critic_required_for", []))
    if brain_critic != policy_critic:
        errors.append(
            "brain.schema.yaml:policies.require_critic_for must match orchestrator/policies.yaml verification_policy.critic_required_for"
        )

    brain_hitl = set(brain.get("policies", {}).get("require_human_approval_for", []))
    policy_hitl = set(policies.get("human_in_the_loop", {}).get("required_for", []))
    if brain_hitl != policy_hitl:
        errors.append(
            "brain.schema.yaml:policies.require_human_approval_for must match orchestrator/policies.yaml human_in_the_loop.required_for"
        )

    brain_tier = brain.get("repository_profile", {}).get("distribution_tier")
    packaging_profile = policies.get("packaging_profile", {})
    policy_tier = packaging_profile.get("active_tier")
    tier_defs = packaging_profile.get("tiers", {})
    if brain_tier and brain_tier not in PACKAGING_TIERS:
        errors.append(f"brain.schema.yaml:repository_profile.distribution_tier has unsupported tier `{brain_tier}`")
    if policy_tier and policy_tier not in PACKAGING_TIERS:
        errors.append(f"orchestrator/policies.yaml:packaging_profile.active_tier has unsupported tier `{policy_tier}`")
    if brain_tier and policy_tier and brain_tier != policy_tier:
        errors.append("brain.schema.yaml:repository_profile.distribution_tier must match orchestrator/policies.yaml packaging_profile.active_tier")
    for tier_name in PACKAGING_TIERS:
        if tier_name not in tier_defs:
            errors.append(f"orchestrator/policies.yaml:packaging_profile.tiers is missing `{tier_name}`")
    allowed_modes = set(tier_defs.get(policy_tier or "", {}).get("allowed_remote_transport_modes", []))
    remote_mode = policies.get("remote_worker_policy", {}).get("transport_mode")
    if policy_tier == "community" and remote_mode and remote_mode != "shared_filesystem_fabric":
        errors.append("orchestrator/policies.yaml:community tier must use shared_filesystem_fabric as the configured remote transport")
    if remote_mode and allowed_modes and remote_mode not in allowed_modes:
        errors.append("orchestrator/policies.yaml:remote_worker_policy.transport_mode must be allowed by the active packaging tier")

    schema_refs = policies.get("blackboard_policy", {}).get("event_schema_refs", {})
    event_types = set(policies.get("blackboard_policy", {}).get("event_types", []))
    for event_type, ref in schema_refs.items():
        if event_type not in event_types:
            errors.append(f"orchestrator/policies.yaml:blackboard_policy.event_schema_refs includes undeclared event type `{event_type}`")
        if not (root / ref).exists():
            errors.append(f"Missing event schema for {event_type}: {ref}")

    validation = brain.get("validation", {})
    for script_key in ("audit_script", "bootstrap_script", "validator_script", "simulation_script"):
        script_path = validation.get(script_key)
        if script_path and not (root / script_path).exists():
            errors.append(f"brain.schema.yaml:validation.{script_key} points to missing file `{script_path}`")

    agents = load_yaml_file(root / "capabilities/agents.yaml").get("agents", [])
    skills = load_yaml_file(root / "capabilities/skills.yaml").get("skills", [])
    plugins = load_yaml_file(root / "capabilities/plugins.yaml").get("plugins", [])
    mcp_entries = load_yaml_file(root / "capabilities/mcp.yaml").get("mcp_entries", [])
    cli_entries = load_yaml_file(root / "capabilities/cli.yaml").get("cli_entries", [])
    models = load_yaml_file(root / "capabilities/models.yaml").get("models", [])

    add_duplicate_errors(errors, "capabilities/agents.yaml", agents, "agent_id")
    add_duplicate_errors(errors, "capabilities/skills.yaml", skills, "skill_id")
    add_duplicate_errors(errors, "capabilities/plugins.yaml", plugins, "plugin_id")
    add_duplicate_errors(errors, "capabilities/mcp.yaml", mcp_entries, "mcp_id")
    add_duplicate_errors(errors, "capabilities/cli.yaml", cli_entries, "cli_id")
    add_duplicate_errors(errors, "capabilities/models.yaml", models, "model_id")

    add_missing_local_path_errors(root, errors, "capabilities/agents.yaml", agents, "agent_id")
    add_missing_local_path_errors(root, errors, "capabilities/skills.yaml", skills, "skill_id")
    add_missing_local_path_errors(root, errors, "capabilities/plugins.yaml", plugins, "plugin_id")
    add_missing_local_path_errors(root, errors, "capabilities/mcp.yaml", mcp_entries, "mcp_id")
    add_missing_local_path_errors(root, errors, "capabilities/cli.yaml", cli_entries, "cli_id")

    for model in models:
        tier = model.get("tier")
        model_id = model.get("model_id", "unknown-model")
        if tier and tier not in MODEL_TIERS:
            errors.append(f"capabilities/models.yaml: model `{model_id}` has unsupported tier `{tier}`")

    discovery_summary = brain.get("discovery_summary", {})
    combined_counts = discovery_summary.get("combined_counts", {})
    expected_counts = {
        "agents": len(agents),
        "skills": len(skills),
        "plugins": len(plugins),
        "mcp_entries": len(mcp_entries),
        "cli_entries": len(cli_entries),
        "models": len(models),
    }
    for key, expected in expected_counts.items():
        actual = combined_counts.get(key)
        if actual is not None and actual != expected:
            errors.append(
                f"brain.schema.yaml:discovery_summary.combined_counts.{key}={actual} does not match current registry count {expected}"
            )

    return errors


def run_validation(root: Path) -> list[str]:
    errors: list[str] = []
    for yaml_rel, schema_rel in FILE_SCHEMA_MAP.items():
        yaml_path = root / yaml_rel
        schema_path = root / schema_rel
        if not yaml_path.exists():
            errors.append(f"Missing file: {yaml_rel}")
            continue
        if not schema_path.exists():
            errors.append(f"Missing schema: {schema_rel}")
            continue
        errors.extend(validate_file(root, yaml_path, schema_path))

    errors.extend(semantic_checks(root))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate portable brain YAML files against JSON Schemas.")
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    errors = run_validation(root)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
