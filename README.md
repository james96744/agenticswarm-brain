# AgenticSwarm Brain

Portable, repo-aware orchestration infrastructure for turning a codebase into a self-maintaining multi-agent brain.

This project is not just a prompt pack or a tool list. It is a file-first orchestration system that discovers the capabilities around a repository, maps them into a runtime, executes work through guarded control-plane flows, learns from route outcomes, and keeps the whole system inspectable.

## What This Repository Is

AgenticSwarm Brain is designed to be copied into another repository and used as that repository's orchestration substrate.

It provides:

- repository and environment discovery
- capability registries for agents, skills, plugins, MCP, CLI tools, and models
- runtime planning and direct execution adapters
- direct invocation for CLI, HTTP-backed MCP, plugin, and queued remote-worker paths
- a blackboard and control plane for events, runs, approvals, artifacts, and leases
- a scheduler abstraction for deferred and remote-worker queue processing
- a transport abstraction for remote workers, with shared-fabric and Redis-broker backends
- git-aware self-maintenance and featureset refresh
- learning surfaces for route replay, benchmark scoring, verified route preferences, and training triplets
- anatomy-based wrapper entrypoints so the system can think in brain terms without renaming the real implementation

The result is a reusable brain scaffold that can be installed into many repos and then adapt itself to each one.

## Distribution Tiers

The architecture is now packaged explicitly in three tiers:

- `Community`: filesystem-only remote transport, no external services, zero-hosting default
- `Advanced`: same free core plus optional BYO Redis broker for stronger cross-host dispatch
- `Enterprise`: reserved pluggable-broker tier for future NATS/SQS-style transports

The active tier is declared in [`orchestrator/policies.yaml`](./orchestrator/policies.yaml) under `packaging_profile.active_tier` and mirrored in [`brain.schema.yaml`](./brain.schema.yaml) as `repository_profile.distribution_tier`.

## Core Idea

The architecture is organized as a literal brain model and enforced in the manifest, policy layer, validation rules, and wrapper registry.

- `Cerebrum`: primary orchestration, planning, routing, and final authority
- `Cerebellum`: secondary decision-making, critique, refinement, and route correction
- `Limbic System`: memory, contradiction tracking, replay, and approval context
- `Neurons`: bounded specialist agents and execution workers
- `Dendrites`: skills, plugins, MCP servers, CLI tools, and backend connectors
- `Brainstem`: runtime bridge, blackboard, control plane, approvals, and artifact transport back to orchestration

This model is backed by:

- [`brain.schema.yaml`](./brain.schema.yaml)
- [`orchestrator/policies.yaml`](./orchestrator/policies.yaml)
- [`orchestrator/anatomy_registry.yaml`](./orchestrator/anatomy_registry.yaml)

## What It Can Do Today

### Discovery And Registry Building

The brain can inspect:

- repository-local agents and skills
- global agent and skill surfaces
- plugins and MCP configurations
- CLI tools and execution backends
- model inventory and runtime candidates
- repository memory, test, build, and deployment signals

It writes those findings into portable registries under [`capabilities/`](./capabilities).

### Runtime Planning And Execution

The runtime layer can:

- resolve discovered inventory into executor, router, and backend candidates
- plan task-family-specific execution bundles
- invoke selected executors and backends directly
- queue deferred and remote-worker dispatch through a file-first scheduler
- dispatch remote-worker tasks into a shared transport fabric and import remote results back into the queue ledger
- switch the remote-worker transport backend between shared filesystem and Redis without changing scheduler or worker entrypoints
- gate risky or high-impact execution behind approvals
- record runs, artifacts, backend calls, critic outcomes, latency, replay score, and verified execution telemetry
- rebuild benchmark rollups and preferred route bundles from accumulated verified telemetry

Key runtime components:

- [`scripts/runtime_bridge.py`](./scripts/runtime_bridge.py)
- [`scripts/execution_engine.py`](./scripts/execution_engine.py)
- [`scripts/execute_task.py`](./scripts/execute_task.py)
- [`scripts/run_scheduler.py`](./scripts/run_scheduler.py)
- [`scripts/run_remote_worker.py`](./scripts/run_remote_worker.py)
- [`scripts/maintain_approvals.py`](./scripts/maintain_approvals.py)
- [`scripts/rebuild_learning.py`](./scripts/rebuild_learning.py)
- [`capabilities/runtime.yaml`](./capabilities/runtime.yaml)

### Control Plane And Blackboard

The system includes a durable file-first coordination layer:

- [`telemetry/blackboard.yaml`](./telemetry/blackboard.yaml): append-only event log
- [`telemetry/control_plane.yaml`](./telemetry/control_plane.yaml): tasks, runs, approvals, artifacts, leases, queue items, workers
- [`scripts/control_plane.py`](./scripts/control_plane.py): store interfaces and lease handling
- [`scripts/operator_status.py`](./scripts/operator_status.py): compact operator view

This gives the brain stable coordination even before Redis/Postgres adapters exist.

### Git-Aware Self-Maintenance

The updater can:

- inspect branch, head, upstream, ahead/behind, and dirty state
- ignore generated brain artifacts via explicit dirty-policy rules
- refresh the featureset when git state changes
- fast-forward safely when the repo is behind and clean

Relevant files:

- [`scripts/update_featureset.py`](./scripts/update_featureset.py)
- [`orchestrator/autopilot.yaml`](./orchestrator/autopilot.yaml)
- [`telemetry/autopilot_state.yaml`](./telemetry/autopilot_state.yaml)

### Learning And Replay

The current scaffold records enough information to support:

- route replay
- benchmark rollups by task family
- verified route preferences ranked from real execution history
- critic pass/fail tracking
- contradiction-aware memory updates
- training triplet accumulation

Relevant files:

- [`telemetry/routes.yaml`](./telemetry/routes.yaml)
- [`capabilities/benchmarks.yaml`](./capabilities/benchmarks.yaml)
- [`memory/facts.yaml`](./memory/facts.yaml)
- [`memory/conflicts.yaml`](./memory/conflicts.yaml)

## Repository Layout

```text
capabilities/   discovered and portable registries
memory/         facts, contradictions, and memory state
orchestrator/   root policy, autopilot, anatomy registry
schemas/        JSON Schemas for every portable contract
scripts/        discovery, runtime, execution, validation, maintenance
simulation/     synthetic scenario inputs
telemetry/      route history, control plane, blackboard, audit state
training/       adapter and distillation job planning
```

## Main Entry Points

### Core

- [`bootstrap.sh`](./bootstrap.sh): installer bootstrap
- [`install_brain.py`](./install_brain.py): copies the scaffold into a target repo
- [`scripts/run_audit.py`](./scripts/run_audit.py): top-level audit, validation, maintenance, and autostart flow
- [`scripts/bootstrap_brain.py`](./scripts/bootstrap_brain.py): discovery and registry population engine
- [`scripts/validate_brain.py`](./scripts/validate_brain.py): schema and semantic validation

### Runtime

- [`scripts/runtime_bridge.py`](./scripts/runtime_bridge.py): runtime registry and planning
- [`scripts/execute_task.py`](./scripts/execute_task.py): live execution entrypoint
- [`scripts/run_scheduler.py`](./scripts/run_scheduler.py): queue dispatcher and remote-result importer
- [`scripts/run_remote_worker.py`](./scripts/run_remote_worker.py): remote-fabric worker poller
- [`scripts/maintain_approvals.py`](./scripts/maintain_approvals.py): stale approval expiry and approval-state cleanup
- [`scripts/operator_status.py`](./scripts/operator_status.py): runtime and learning summary
- [`scripts/rebuild_learning.py`](./scripts/rebuild_learning.py): rebuild benchmark rollups and replay preferences from route history
- [`scripts/update_featureset.py`](./scripts/update_featureset.py): git-aware featureset refresh

### Anatomy Wrappers

The project includes stable anatomy-named wrappers over the implementation modules:

- [`scripts/cerebrum.py`](./scripts/cerebrum.py)
- [`scripts/cerebellum.py`](./scripts/cerebellum.py)
- [`scripts/limbic_system.py`](./scripts/limbic_system.py)
- [`scripts/neurons.py`](./scripts/neurons.py)
- [`scripts/dendrites.py`](./scripts/dendrites.py)
- [`scripts/brainstem.py`](./scripts/brainstem.py)

The wrapper-to-module mapping is declared in [`orchestrator/anatomy_registry.yaml`](./orchestrator/anatomy_registry.yaml), and all wrapper actions can be exercised end-to-end with [`scripts/verify_anatomy_wrappers.py`](./scripts/verify_anatomy_wrappers.py).

## Quick Start

### 1. Install Into A Repository

Install into the current directory:

```bash
curl -fsSL https://raw.githubusercontent.com/james96744/agenticswarm-brain/main/bootstrap.sh | bash -s -- .
```

Install into another repository:

```bash
curl -fsSL https://raw.githubusercontent.com/james96744/agenticswarm-brain/main/bootstrap.sh | bash -s -- /path/to/repo
```

Or from a local clone:

```bash
python3 install_brain.py --target /path/to/repo
```

### 2. Create A Local Environment

Inside the target repository:

```bash
python3 -m venv .venv
./.venv/bin/pip install pyyaml jsonschema
```

### 3. Run The First Audit

Dry-run first:

```bash
./.venv/bin/python scripts/run_audit.py --repo-root . --dry-run --no-autostart
```

Then populate:

```bash
./.venv/bin/python scripts/run_audit.py --repo-root .
```

That first audit handles discovery, validation, runtime checks, maintenance, telemetry initialization, and supported autostart installation.

## Typical Workflows

### Plan Runtime Paths

```bash
./.venv/bin/python scripts/runtime_bridge.py --repo-root . --dry-run
```

### Execute A Real Task

```bash
./.venv/bin/python scripts/execute_task.py --repo-root . --request-file request.yaml
```

### Check Operator State

```bash
./.venv/bin/python scripts/operator_status.py --repo-root .
```

### Refresh The Featureset Safely

```bash
./.venv/bin/python scripts/update_featureset.py --repo-root . --dry-run
```

### Process Deferred Or Remote Work

```bash
./.venv/bin/python scripts/run_scheduler.py --repo-root . --dry-run
./.venv/bin/python scripts/run_scheduler.py --repo-root . --dispatch-mode remote_worker --process-limit 1
./.venv/bin/python scripts/run_remote_worker.py --repo-root . --process-limit 1
```

The scheduler can dispatch `remote_worker` jobs either into the shared fabric under [`telemetry/remote_fabric`](./telemetry/remote_fabric) or into a Redis broker when the active packaging tier allows it and `remote_worker_policy.transport_mode` is set to `redis_broker`. The remote worker consumes those transport envelopes, executes them, and writes results back for the scheduler to reconcile into the control plane.

### Expire Stale Approvals

```bash
./.venv/bin/python scripts/maintain_approvals.py --repo-root . --dry-run
./.venv/bin/python scripts/maintain_approvals.py --repo-root .
```

This converts stale pending approvals into explicit `expired` state and closes the corresponding approval-gated dispatch runs instead of leaving them permanently pending.

### Rebuild Learning From Verified Telemetry

```bash
./.venv/bin/python scripts/rebuild_learning.py --repo-root . --dry-run
./.venv/bin/python scripts/rebuild_learning.py --repo-root .
```

This compacts accumulated real execution telemetry into refreshed benchmark rollups and ranked `route_preferences` inside [`telemetry/routes.yaml`](./telemetry/routes.yaml), which the planner can then reuse for replay-aware routing.

### Exercise Anatomy Wrappers

```bash
./.venv/bin/python scripts/verify_anatomy_wrappers.py --repo-root .
```

## Anatomy Wrapper Examples

Use anatomy terms directly:

```bash
./.venv/bin/python scripts/cerebrum.py audit --repo-root . --dry-run --no-autostart
./.venv/bin/python scripts/cerebrum.py plan --repo-root . --dry-run
./.venv/bin/python scripts/cerebellum.py validate --repo-root .
./.venv/bin/python scripts/dendrites.py refresh --repo-root . --dry-run
./.venv/bin/python scripts/neurons.py execute --repo-root . --request-file request.yaml
./.venv/bin/python scripts/brainstem.py status --repo-root .
```

These wrappers are aliases, not alternate implementations. The real logic still lives in the underlying modules, which keeps the implementation stable while allowing the orchestration layer to reason in anatomy terms.

## Safety Model

The scaffold defaults to guarded autonomy.

- destructive, high-risk, deployment, and security-sensitive paths can require approval
- critic review is enforced for important task families
- capability selection is policy-driven and provenance-aware
- memory contradictions are tracked instead of silently reused
- generated state is separated from source state so auto-update behavior remains safe

The main safety and behavior contracts live in:

- [`orchestrator/policies.yaml`](./orchestrator/policies.yaml)
- [`orchestrator/autopilot.yaml`](./orchestrator/autopilot.yaml)
- [`scripts/validate_brain.py`](./scripts/validate_brain.py)

## Validation And CI

The project validates:

- all portable YAML registries against JSON Schema
- semantic alignment between manifest, policy, and anatomy layers
- runtime wrapper registration and module existence
- blackboard event schema references and script path integrity

Use:

```bash
./.venv/bin/python scripts/validate_brain.py --repo-root .
```

The repository also includes CI validation via [`.github/workflows/brain-validate.yml`](./.github/workflows/brain-validate.yml).

## Why The Design Is File-First

The current implementation uses files as the system of record because it is:

- portable across repos
- easy to inspect and diff
- simple to validate
- low-friction for local development
- a clean foundation for later storage adapters

Redis/Postgres-style backends can be added later behind the same interfaces without changing the top-level contracts.

## Current Status

The repository currently provides:

- a portable orchestration scaffold
- a capability inventory system
- a live runtime planning and execution layer
- a durable blackboard and control plane
- an anatomy-based orchestration model with wrapper entrypoints
- git-aware self-maintenance, queued remote work, and replay-aware learning surfaces

The main expansion areas from here are even broader backend adapters, richer remote-worker transport beyond the local file-first scheduler, and larger-scale verified telemetry ingestion for future route adaptation.

## Repository

GitHub: [james96744/agenticswarm-brain](https://github.com/james96744/agenticswarm-brain)
