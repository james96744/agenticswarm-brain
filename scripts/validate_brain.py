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
    "capabilities/brain_network.yaml": "schemas/capabilities/brain_network.schema.json",
    "capabilities/brain_network_install_profiles.yaml": "schemas/capabilities/brain_network_install_profiles.schema.json",
    "capabilities/cli.yaml": "schemas/capabilities/cli.schema.json",
    "capabilities/mcp.yaml": "schemas/capabilities/mcp.schema.json",
    "capabilities/models.yaml": "schemas/capabilities/models.schema.json",
    "capabilities/plugins.yaml": "schemas/capabilities/plugins.schema.json",
    "capabilities/runtime.yaml": "schemas/capabilities/runtime.schema.json",
    "capabilities/skills.yaml": "schemas/capabilities/skills.schema.json",
    "memory/conflicts.yaml": "schemas/memory/conflicts.schema.json",
    "memory/facts.yaml": "schemas/memory/facts.schema.json",
    "memory/portable_memory.yaml": "schemas/memory/portable_memory.schema.json",
    "memory/product_context.yaml": "schemas/memory/product_context.schema.json",
    "memory/user_profile.yaml": "schemas/memory/user_profile.schema.json",
    "orchestrator/autopilot.yaml": "schemas/orchestrator/autopilot.schema.json",
    "orchestrator/anatomy_registry.yaml": "schemas/orchestrator/anatomy_registry.schema.json",
    "orchestrator/policies.yaml": "schemas/orchestrator/policies.schema.json",
    "simulation/scenarios.yaml": "schemas/simulation/scenarios.schema.json",
    "telemetry/audit_report.yaml": "schemas/telemetry/audit_report.schema.json",
    "telemetry/autopilot_state.yaml": "schemas/telemetry/autopilot_state.schema.json",
    "telemetry/blackboard.yaml": "schemas/telemetry/blackboard.schema.json",
    "telemetry/brain_network_installs.yaml": "schemas/telemetry/brain_network_installs.schema.json",
    "telemetry/control_plane.yaml": "schemas/telemetry/control_plane.schema.json",
    "telemetry/discovery_state.yaml": "schemas/telemetry/discovery_state.schema.json",
    "telemetry/routes.yaml": "schemas/telemetry/routes.schema.json",
    "telemetry/transplant_history.yaml": "schemas/telemetry/transplant_history.schema.json",
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
OPTIONAL_LOCAL_PATH_PREFIXES = (".venv/", ".brain_integrations/")


def is_optional_local_path(path_value: str) -> bool:
    normalized = path_value.replace("\\", "/")
    return normalized.startswith(OPTIONAL_LOCAL_PATH_PREFIXES)


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
        if not (root / path_value).exists() and not is_optional_local_path(path_value):
            errors.append(f"{label}: local entry `{item.get(key, 'unknown')}` points to missing path `{path_value}`")


def semantic_checks(root: Path) -> list[str]:
    errors = []
    brain_data = load_yaml_file(root / "brain.schema.yaml")
    brain = brain_data.get("brain_manifest", {})
    anatomy_registry_ref = brain.get("anatomy_registry", {}).get("path", "orchestrator/anatomy_registry.yaml")
    anatomy_registry = load_yaml_file(root / anatomy_registry_ref)
    brain_network_ref = brain.get("brain_network_registry", {}).get("path", "capabilities/brain_network.yaml")
    brain_network = load_yaml_file(root / brain_network_ref)
    install_profiles_ref = brain.get("brain_network_install_profiles", {}).get("path", "capabilities/brain_network_install_profiles.yaml")
    install_profiles_payload = load_yaml_file(root / install_profiles_ref)
    install_state_ref = brain.get("brain_network_install_state", {}).get("path", "telemetry/brain_network_installs.yaml")
    sovereign_memory = brain.get("sovereign_memory", {})
    user_profile_ref = sovereign_memory.get("user_profile_path", "memory/user_profile.yaml")
    product_context_ref = sovereign_memory.get("product_context_path", "memory/product_context.yaml")
    portable_memory_ref = sovereign_memory.get("portable_memory_path", "memory/portable_memory.yaml")
    transplant_history_ref = sovereign_memory.get("transplant_history_path", "telemetry/transplant_history.yaml")
    transplant_script_ref = sovereign_memory.get("transplant_script", "scripts/transplant_brain.py")
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

    if brain_network_ref and not (root / brain_network_ref).exists():
        errors.append(f"brain.schema.yaml:brain_network_registry.path points to missing file `{brain_network_ref}`")
    if install_profiles_ref and not (root / install_profiles_ref).exists():
        errors.append(f"brain.schema.yaml:brain_network_install_profiles.path points to missing file `{install_profiles_ref}`")
    if install_state_ref and not (root / install_state_ref).exists():
        errors.append(f"brain.schema.yaml:brain_network_install_state.path points to missing file `{install_state_ref}`")
    for label, ref in (
        ("user_profile_path", user_profile_ref),
        ("product_context_path", product_context_ref),
        ("portable_memory_path", portable_memory_ref),
        ("transplant_history_path", transplant_history_ref),
        ("transplant_script", transplant_script_ref),
    ):
        if ref and not (root / ref).exists():
            errors.append(f"brain.schema.yaml:sovereign_memory.{label} points to missing path `{ref}`")

    integrations = brain_network.get("integrations", [])
    bundles = brain_network.get("bundles", [])
    install_profiles = install_profiles_payload.get("profiles", [])
    add_duplicate_errors(errors, "capabilities/brain_network.yaml", integrations, "integration_id")
    add_duplicate_errors(errors, "capabilities/brain_network_install_profiles.yaml", install_profiles, "integration_id")
    known_integration_ids = {item.get("integration_id") for item in integrations if item.get("integration_id")}
    known_profile_ids = {item.get("integration_id") for item in install_profiles if item.get("integration_id")}
    for bundle in bundles:
        bundle_id = bundle.get("bundle_id", "unknown-bundle")
        for integration_id in bundle.get("integration_ids", []):
            if integration_id not in known_integration_ids:
                errors.append(
                    f"capabilities/brain_network.yaml: bundle `{bundle_id}` references unknown integration `{integration_id}`"
                )
    for integration_id in sorted(known_integration_ids - known_profile_ids):
        errors.append(f"capabilities/brain_network_install_profiles.yaml: missing install profile for integration `{integration_id}`")
    for integration_id in sorted(known_profile_ids - known_integration_ids):
        errors.append(f"capabilities/brain_network_install_profiles.yaml: profile exists for unknown integration `{integration_id}`")

    curated_registry_path = policies.get("brain_network_policy", {}).get("curated_registry_path")
    if curated_registry_path and curated_registry_path != brain_network_ref:
        errors.append("orchestrator/policies.yaml:brain_network_policy.curated_registry_path must match brain.schema.yaml brain_network_registry.path")

    brain_tier = brain.get("repository_profile", {}).get("distribution_tier")
    packaging_profile = policies.get("packaging_profile", {})
    transplant_policy = policies.get("transplant_policy", {})
    sovereign_policy = policies.get("sovereign_product_brain_policy", {})
    memory_classification_policy = policies.get("memory_classification_policy", {})
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
    if not sovereign_policy.get("always_on", False):
        errors.append("orchestrator/policies.yaml:sovereign_product_brain_policy.always_on must be true")
    if not memory_classification_policy.get("explicit_classification_required", False):
        errors.append("orchestrator/policies.yaml:memory_classification_policy.explicit_classification_required must be true")
    if not transplant_policy.get("enabled", False):
        errors.append("orchestrator/policies.yaml:transplant_policy.enabled must be true")
    if not transplant_policy.get("local_target_only", False):
        errors.append("orchestrator/policies.yaml:transplant_policy.local_target_only must be true for the current implementation")

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
