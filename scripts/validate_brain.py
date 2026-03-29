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
    "capabilities/skills.yaml": "schemas/capabilities/skills.schema.json",
    "memory/conflicts.yaml": "schemas/memory/conflicts.schema.json",
    "memory/facts.yaml": "schemas/memory/facts.schema.json",
    "orchestrator/autopilot.yaml": "schemas/orchestrator/autopilot.schema.json",
    "orchestrator/policies.yaml": "schemas/orchestrator/policies.schema.json",
    "simulation/scenarios.yaml": "schemas/simulation/scenarios.schema.json",
    "telemetry/audit_report.yaml": "schemas/telemetry/audit_report.schema.json",
    "telemetry/autopilot_state.yaml": "schemas/telemetry/autopilot_state.schema.json",
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
    policies = load_yaml_file(root / "orchestrator/policies.yaml")

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
