# Usage

This project is a portable orchestration scaffold. It is designed to be copied into a repository, pointed at that repository, and then used to discover capabilities, validate contracts, simulate routing, reconcile memory, and prepare optimization workflows.

## 1. Create A Local Environment

If you are installing the brain into another repo, the quickest path is:

```bash
curl -fsSL https://raw.githubusercontent.com/james96744/agenticswarm-brain/main/bootstrap.sh | bash -s -- /path/to/your/repo
```

Then move into the target repo and create a local environment:

```bash
python3 -m venv .venv
./.venv/bin/pip install pyyaml jsonschema
```

These packages are required for YAML loading and schema validation.

## 2. Run The Auditor Once

Use this first:

```bash
./.venv/bin/python scripts/run_audit.py --repo-root . --dry-run
```

This performs one full audit pass without changing files:

- discovers repository-local agents, skills, plugins, MCPs, and CLIs
- discovers globally installed agents, skills, plugins, MCP configs, MCP executables, models, and CLIs
- compiles every Python script under `scripts/`
- validates all YAML registries and semantic cross-file rules
- dry-runs the runtime sanity checks for git-aware featureset updates, simulation, reconciliation, pruning, and distillation prep

When the report looks correct, populate the registries and write an audit report:

```bash
./.venv/bin/python scripts/run_audit.py --repo-root .
```

This updates:

- [`brain.schema.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/brain.schema.yaml)
- [`capabilities/agents.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/capabilities/agents.yaml)
- [`capabilities/skills.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/capabilities/skills.yaml)
- [`capabilities/plugins.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/capabilities/plugins.yaml)
- [`capabilities/mcp.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/capabilities/mcp.yaml)
- [`capabilities/cli.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/capabilities/cli.yaml)
- [`capabilities/models.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/capabilities/models.yaml)
- [`capabilities/runtime.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/capabilities/runtime.yaml)
- [`telemetry/audit_report.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/telemetry/audit_report.yaml)
- [`telemetry/discovery_state.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/telemetry/discovery_state.yaml)
- [`telemetry/autopilot_state.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/telemetry/autopilot_state.yaml)

After that first non-dry run, the brain takes over:

- it installs automatic startup rechecks on supported platforms
- it rechecks previously discovered install roots automatically
- it triggers a full refresh when new installs or removed integrations are detected
- it checks git branch, head, and upstream state and refreshes the featureset automatically
- it runs maintenance phases automatically without separate commands

Use `--skip-runtime-checks` only for a lighter first pass. Use `--no-autostart` only for CI or testing.

## 3. Startup Behavior

After the first full audit, the runner records discovery watch roots in [`telemetry/discovery_state.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/telemetry/discovery_state.yaml) and autopilot installation state in [`telemetry/autopilot_state.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/telemetry/autopilot_state.yaml).

What it does:

- rechecks the previously discovered repo-local and global watch directories
- detects new installs, removed integrations, or modified capability roots
- runs a full repopulating audit automatically if something changed
- skips the heavy full discovery pass when nothing changed
- checks git state and can fast-forward safely when the worktree is clean
- runs memory reconciliation, topology pruning, and distillation preparation automatically

The internal `--startup-check` mode is now meant for the installed autopilot adapter rather than normal manual use.

## 4. Validate The Portable Contracts

Run:

```bash
./.venv/bin/python scripts/validate_brain.py --repo-root .
```

Expected result:

- `Validation passed.`

This checks the YAML registries against the JSON Schemas and verifies that the root manifest and runtime policy stay aligned.

## 5. Inspect A Repository Without Changing It

Use a dry run first:

```bash
./.venv/bin/python scripts/bootstrap_brain.py --repo-root . --dry-run
```

This reports:

- detected repository name
- inferred stack
- inferred risk level
- counts for discovered agents, skills, plugins, MCPs, CLIs, and models

Use this first whenever you are pointing the orchestrator at a new repository.

## 5A. Use Anatomy-Named Wrappers

The brain now has a stable anatomy-to-module registry in [`orchestrator/anatomy_registry.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/orchestrator/anatomy_registry.yaml) plus optional wrapper entrypoints:

- [`scripts/cerebrum.py`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/scripts/cerebrum.py)
- [`scripts/cerebellum.py`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/scripts/cerebellum.py)
- [`scripts/limbic_system.py`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/scripts/limbic_system.py)
- [`scripts/neurons.py`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/scripts/neurons.py)
- [`scripts/dendrites.py`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/scripts/dendrites.py)
- [`scripts/brainstem.py`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/scripts/brainstem.py)

Examples:

```bash
./.venv/bin/python scripts/cerebrum.py plan --repo-root . --dry-run
./.venv/bin/python scripts/cerebellum.py validate --repo-root .
./.venv/bin/python scripts/brainstem.py status --repo-root .
./.venv/bin/python scripts/neurons.py execute --repo-root . --request-file request.yaml
```

These wrappers do not replace the implementation modules. They provide stable brain-anatomy aliases over them.

To verify the full anatomy wrapper surface end to end, run:

```bash
./.venv/bin/python scripts/verify_anatomy_wrappers.py --repo-root .
```

This exercises every registered wrapper action, including safe execution paths for `neurons` and `brainstem`.

## 6. Populate The Capability Registries

When the dry run looks correct, write the discovered state into the portable registries:

```bash
./.venv/bin/python scripts/bootstrap_brain.py --repo-root .
```

This updates:

- [`brain.schema.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/brain.schema.yaml)
- [`capabilities/agents.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/capabilities/agents.yaml)
- [`capabilities/skills.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/capabilities/skills.yaml)
- [`capabilities/plugins.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/capabilities/plugins.yaml)
- [`capabilities/mcp.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/capabilities/mcp.yaml)
- [`capabilities/cli.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/capabilities/cli.yaml)
- [`capabilities/models.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/capabilities/models.yaml)
- [`capabilities/runtime.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/capabilities/runtime.yaml)

## 7. Re-Validate After Discovery

Run:

```bash
./.venv/bin/python scripts/validate_brain.py --repo-root .
```

This confirms the discovered output is still schema-safe.

## 7A. Check Git And Refresh The Featureset

Use the git-aware updater directly when you want a targeted refresh:

```bash
./.venv/bin/python scripts/update_featureset.py --repo-root . --dry-run
```

When not in dry-run mode, it:

- records current branch, head SHA, upstream ref, ahead/behind counts, and dirty state
- fetches upstream when configured
- refreshes discovered capabilities when git state changes
- fast-forwards with `git pull --ff-only` only when the repo is behind and the worktree is clean

This step also runs automatically from the audit maintenance loop when `maintenance.update_featureset` is enabled in [`orchestrator/autopilot.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/orchestrator/autopilot.yaml).

## 8. Exercise The Routing Policy

Use the simulation harness first:

```bash
./.venv/bin/python scripts/simulate_swarm.py --repo-root . --dry-run
```

When the routes look reasonable, write them into telemetry:

```bash
./.venv/bin/python scripts/simulate_swarm.py --repo-root .
```

This appends simulated route records into [`telemetry/routes.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/telemetry/routes.yaml).

## 9. Execute A Real Task Through The Control Plane

Create a task request file in YAML or JSON with the normalized execution contract. Example:

```yaml
task_id: safe-exec-demo
task_family: boilerplate_code
description: Verify executor and backend invocation.
risk_level: low
selected_executor_id: python-workflow-runner
selected_backend_ids:
  - cli-rg
inputs:
  command:
    argv: ["python3", "-c", "print('executor ok')"]
  backend_requests:
    - backend_id: cli-rg
      args: ["--files"]
```

Run it with:

```bash
./.venv/bin/python scripts/execute_task.py --repo-root . --request-file request.yaml
```

This writes live task, run, approval, artifact, and event data into:

- [`telemetry/blackboard.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/telemetry/blackboard.yaml)
- [`telemetry/control_plane.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/telemetry/control_plane.yaml)
- [`telemetry/routes.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/telemetry/routes.yaml)
- [`capabilities/benchmarks.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/capabilities/benchmarks.yaml)
- [`memory/facts.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/memory/facts.yaml)
- [`memory/conflicts.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/memory/conflicts.yaml)

High-risk tasks, destructive actions, writes, deploys, and auth-scoped backends are gated and recorded as pending approvals instead of auto-running.

## 10. Inspect Runtime Health And Operator State

Use:

```bash
./.venv/bin/python scripts/operator_status.py --repo-root .
```

This reports:

- runtime executor/router/backend readiness
- recent runs and failures
- pending approvals
- route replay quality
- benchmark and learning rollups

## 11. Reconcile Memory Conflicts

Populate [`memory/facts.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/memory/facts.yaml) with fact records, then run:

```bash
./.venv/bin/python scripts/reconcile_memory.py --repo-root .
```

Detected contradictions are written to [`memory/conflicts.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/memory/conflicts.yaml).

Use this when:

- two agents disagree about a variable or artifact state
- route memory conflicts with recent telemetry
- capability metadata contradicts runtime policy

## 12. Generate Merge And Prune Recommendations

Populate benchmark telemetry in [`capabilities/benchmarks.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/capabilities/benchmarks.yaml), then run:

```bash
./.venv/bin/python scripts/prune_topology.py --repo-root .
```

This writes merge or prune recommendations into [`telemetry/routes.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/telemetry/routes.yaml).

Use this to:

- merge agents with excessive handoff overhead
- identify zombie agents with poor value-add per token

## 13. Prepare Distillation And Adapter Jobs

Populate verified expert-correction triplets inside [`telemetry/routes.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/telemetry/routes.yaml) under `training_triplets`, then run:

```bash
./.venv/bin/python scripts/prepare_distillation.py --repo-root .
```

This updates:

- [`training/jobs.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/training/jobs.yaml)
- [`training/adapters.yaml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/training/adapters.yaml)

Use this when enough verified Tier 3 corrections exist to justify LoRA or adapter training for a task family.

## 14. Run The Full Local Audit Sequence

Use this sequence when adopting the system in a new repository:

```bash
./.venv/bin/python scripts/run_audit.py --repo-root . --dry-run
./.venv/bin/python scripts/run_audit.py --repo-root .
```

Everything after that is automated by the brain.

## 15. Use CI For Ongoing Safety

The repository includes [`.github/workflows/brain-validate.yml`](/Users/j/Desktop/Lahaolesolutions/agenticswarm%20creation/.github/workflows/brain-validate.yml).

That workflow:

- installs validation dependencies
- runs the single audit entrypoint in dry-run mode
- disables autostart so CI does not register a background service

## 16. Recommended Operating Pattern

Use this order in practice:

1. Dry-run the single audit.
2. Run the single audit without `--dry-run` to populate registries, establish watch roots, and install autopilot.
3. Commit discovered registries if they look correct.
4. Let the brain handle startup rechecks and maintenance automatically.
5. Feed real telemetry into benchmarks and memory stores when you want richer optimization.

## Notes

- `run_audit.py` is the main entrypoint for discovery, population, compile checks, validation, maintenance, and autostart installation.
- `bootstrap_brain.py` is the lower-level discovery engine used by the audit runner.
- `update_featureset.py` adds git-aware featureset refresh and safe fast-forward behavior.
- `simulate_swarm.py` exercises policy logic; it does not call real models.
- `prepare_distillation.py` prepares jobs; it does not train adapters itself.
- Keep dry-run as the default for first contact with any unfamiliar repository.
