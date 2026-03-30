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

## At A Glance

- one-command local bring-up with [`run_brain.sh`](./run_brain.sh)
- repo discovery across agents, skills, plugins, MCP, CLI tools, and models
- real execution through executor, router, and backend selection
- durable blackboard and control-plane state for tasks, runs, approvals, artifacts, leases, and queues
- tiered transport packaging: free local/community by default, optional Redis-backed network mode in `advanced`
- verified telemetry rebuild for replay-aware routing and benchmark rollups
- anatomy-based wrapper entrypoints so orchestration can reason in brain terms without renaming implementation modules

## Distribution Tiers

The architecture is now packaged explicitly in three tiers:

- `Community`: filesystem-only remote transport, no external services, zero-hosting default
- `Advanced`: same free core plus optional BYO Redis broker for stronger cross-host dispatch
- `Enterprise`: reserved pluggable-broker tier for future NATS/SQS-style transports

The active tier is declared in [`orchestrator/policies.yaml`](./orchestrator/policies.yaml) under `packaging_profile.active_tier` and mirrored in [`brain.schema.yaml`](./brain.schema.yaml) as `repository_profile.distribution_tier`.

## Local, Shared, And Networked Modes

There are three practical ways to run the brain today:

- `Local workspace`: one repo clone, one machine, one `.venv`, default `community` mode
- `Shared workspace`: multiple workers using the same filesystem fabric, still `community`, useful for a shared volume or LAN-style setup
- `Networked workspace`: multiple independent repo clones connected through a broker, use `advanced` plus BYO Redis

If you want zero ongoing hosting cost, stay on `community`. If you want independent cloud workspaces, remote laptops, or multiple machines without a shared disk, move to `advanced` and bring your own Redis.

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
- invoke selected executors and backends directly instead of only simulating routes
- queue deferred and remote-worker dispatch through a file-first scheduler
- dispatch remote-worker tasks into a shared transport fabric and import remote results back into the queue ledger
- switch the remote-worker transport backend between shared filesystem and Redis without changing scheduler or worker entrypoints
- gate risky or high-impact execution behind approvals
- expire stale approvals and close stranded approval-gated runs cleanly
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

Operator-facing control-plane maintenance now includes:

- pending and expired approval tracking
- queue and worker heartbeat visibility
- linked run and artifact provenance
- remote dispatch reconciliation back into the control plane

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

Those learning surfaces are now fed by real execution telemetry, not only simulated routes.

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
- [`run_brain.sh`](./run_brain.sh): one-command local bootstrap, dependency install, audit, populate, and activation launcher
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

### 2. Run The Brain

Inside the target repository:

```bash
./run_brain.sh --dry-run --no-autostart
```

That single command:

- creates `.venv` if it does not exist
- installs the minimum local Python dependencies automatically
- runs the audit against the current repo
- keeps autostart disabled when you pass `--no-autostart`

For most users, this is the only command needed to bootstrap the local brain.

### 3. Populate And Activate

```bash
./run_brain.sh
```

That first non-dry run handles discovery, population, validation, runtime checks, maintenance, telemetry initialization, and supported autostart installation.

[`scripts/run_audit.py`](./scripts/run_audit.py) is still available directly, but [`run_brain.sh`](./run_brain.sh) is the normal entrypoint.

## Upgrade To Cloud Or Networked Workspaces

Use this when you want the same brain to coordinate work across separate machines, remote devboxes, or cloud workspaces without relying on a shared filesystem.

### 1. Move From `community` To `advanced`

Update the active distribution tier in both files so validation stays aligned:

- [`orchestrator/policies.yaml`](./orchestrator/policies.yaml)
  - set `packaging_profile.active_tier: advanced`
- [`brain.schema.yaml`](./brain.schema.yaml)
  - set `repository_profile.distribution_tier: advanced`

Then switch the remote-worker transport policy:

- [`orchestrator/policies.yaml`](./orchestrator/policies.yaml)
  - set `remote_worker_policy.transport_mode: redis_broker`

### 2. Point The Brain At Your Broker

The current networked backend is Redis. You can configure it in either of two ways:

- preferred: export `REDIS_URL` in each workspace
- fallback: set `remote_worker_policy.redis.url` in [`orchestrator/policies.yaml`](./orchestrator/policies.yaml)

Example `REDIS_URL`:

```bash
export REDIS_URL=redis://127.0.0.1:6379/0
```

If you want to keep this free, self-host Redis yourself. Typical paths are:

- local Docker on your own machine
- a VM you already control
- a home-lab or LAN server

You do not need to pay for a managed cloud broker unless you specifically want that.

### 3. Install The Optional Redis Client In Each Workspace

The base launcher only installs the minimum local dependencies. Redis support needs the Python Redis client:

```bash
./.venv/bin/pip install redis
```

### 4. Bootstrap Each Workspace

Each cloud or remote workspace should have its own repo clone and local environment:

```bash
./run_brain.sh --dry-run --no-autostart
./run_brain.sh --no-autostart
```

That keeps each workspace capable of discovery, validation, execution, and local tool access while sharing remote dispatch through Redis.

### 5. Run The Coordinator

On the machine acting as the cerebrum-side queue dispatcher:

```bash
./.venv/bin/python scripts/run_scheduler.py --repo-root . --dispatch-mode remote_worker --transport-mode redis
```

This takes queued `remote_worker` jobs from the control plane and dispatches them into the broker.

### 6. Run Remote Workers

On each remote machine or cloud workspace:

```bash
./.venv/bin/python scripts/run_remote_worker.py --repo-root . --transport-mode redis --worker-id worker-1
```

Use a distinct `--worker-id` per workspace.

### 7. Verify The Upgrade

Check the live transport and packaging state:

```bash
./.venv/bin/python scripts/operator_status.py --repo-root .
./.venv/bin/python scripts/run_remote_worker.py --repo-root . --dry-run --transport-mode redis
```

You should see:

- `active_tier: advanced`
- `allowed_remote_transport_modes` including `redis_broker`
- transport status with `active_mode: redis_broker`

If Redis is requested but not reachable, the system will report a fallback or restriction reason instead of failing silently.

### Operational Notes

- `community` is still the right default for free local distribution.
- `advanced` is the current path for real networked workspaces.
- `enterprise` is reserved for future broker backends like NATS or SQS; that tier is not the normal path today.
- Workers should each have the repo and any required local tools installed; the broker transports jobs, not full execution environments.
- If multiple machines are meant to execute code, keep repository state synchronized with Git rather than trying to share one `.venv` or one working tree across hosts.

## Typical Workflows

### One-Command Local Bring-Up

```bash
./run_brain.sh --dry-run --no-autostart
./run_brain.sh
```

Use this sequence when installing the brain into a repo for the first time.

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

This is the fastest way to inspect the current packaging tier, transport mode, run counts, approval state, and learning summary.

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
- packaging-tier and remote-transport alignment

Use:

```bash
./.venv/bin/python scripts/validate_brain.py --repo-root .
```

The repository also includes CI validation via [`.github/workflows/brain-validate.yml`](./.github/workflows/brain-validate.yml).

## Why The Design Is File-First

The current implementation keeps the control plane and most registries file-first because it is:

- portable across repos
- easy to inspect and diff
- simple to validate
- low-friction for local development
- a clean foundation for later storage adapters

Remote transport is already allowed to move beyond the filesystem through the broker abstraction. The file-first rule mainly applies to the core system-of-record state, not to every signal path.

## Current Status

The repository currently provides:

- a portable orchestration scaffold
- a capability inventory system across agents, skills, plugins, MCP, CLI tools, and models
- a live runtime planning and execution layer with direct invocation
- a durable blackboard and control plane with approvals, leases, queues, artifacts, and workers
- anatomy-based orchestration with registry-backed wrapper entrypoints
- a one-command local bootstrap path through [`run_brain.sh`](./run_brain.sh)
- git-aware self-maintenance and generated-state-aware dirty handling
- remote-worker dispatch through shared filesystem fabric and optional Redis broker transport
- replay-aware learning surfaces rebuilt from verified execution telemetry

The main expansion areas from here are wider broker coverage beyond Redis, alternative durable state backends beyond the file-first control plane, and larger verified telemetry volumes for stronger route adaptation.

## Repository

GitHub: [james96744/agenticswarm-brain](https://github.com/james96744/agenticswarm-brain)
