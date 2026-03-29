# AgenticSwarm Brain

Portable, repo-aware orchestration scaffold for building a self-maintaining multi-agent brain inside any codebase.

AgenticSwarm Brain is designed to be dropped into a repository, inspect that repository plus the globally installed agent/skill/MCP/CLI/model surface, populate a portable capability graph, and keep itself updated through automated startup rechecks and maintenance.

## What It Does

- Audits any repository it is installed into
- Discovers local and global agents, skills, plugins, MCPs, CLIs, and model surfaces
- Builds portable registries the orchestrator can route against
- Validates schemas and cross-file contract consistency
- Runs maintenance automatically: memory reconciliation, topology pruning, and distillation prep
- Installs background startup rechecks on supported platforms so new installs are detected without manual intervention

## Why This Exists

Most agent frameworks stop at prompts, tools, or task routing. This project is meant to operate more like a reusable orchestration layer:

- portable across repos
- aware of its environment
- able to prefer the cheapest safe execution path
- capable of learning from route history
- structured enough to validate, version, and automate

The goal is not just “run agents.” The goal is to give a repository a persistent, inspectable, self-updating brain.

## Core Capabilities

### Repo-Aware Discovery

The brain inspects:

- repository-local agent definitions
- repository-local skills and scripts
- plugin manifests
- MCP configs and MCP executables
- installed CLI tools
- available model runtimes and cached model catalogs

### Tiered Orchestration

The system is built around:

- semantic routing
- draft-and-verify loops
- worker / critic / expert escalation
- dynamic DAG generation
- historical route replay
- context compression

### Self-Maintenance

After bootstrap, the brain can:

- recheck watched install roots on startup
- detect newly installed capabilities
- refresh capability registries when the environment changes
- reconcile contradictory memory
- recommend topology merges and pruning
- prepare distillation and adapter jobs from correction history

## Install

### One-Line Bootstrap

Install into the current directory:

```bash
curl -fsSL https://raw.githubusercontent.com/james96744/agenticswarm-brain/main/bootstrap.sh | bash -s -- .
```

Install into a specific repository path:

```bash
curl -fsSL https://raw.githubusercontent.com/james96744/agenticswarm-brain/main/bootstrap.sh | bash -s -- /path/to/your/repo
```

### Manual Install

From a local clone of this repository:

```bash
python3 install_brain.py --target /path/to/your/repo
```

## First Run

Inside the target repo:

```bash
python3 -m venv .venv
./.venv/bin/pip install pyyaml jsonschema
./.venv/bin/python scripts/run_audit.py --repo-root .
```

That first real audit:

- installs the scaffold
- performs discovery
- populates capability registries
- validates the system
- runs maintenance
- stores discovery watch roots
- installs background startup rechecks on supported platforms

After that, the brain handles ongoing startup rechecks and maintenance automatically.

## Project Layout

```text
capabilities/   portable registries for agents, skills, plugins, MCPs, CLIs, and models
memory/         fact store and contradiction tracking
orchestrator/   orchestration and autopilot policy
schemas/        JSON Schemas for validation
scripts/        auditor, discovery, validation, maintenance, and simulation tooling
simulation/     synthetic scenario inputs
telemetry/      route history, audit reports, discovery state, autopilot state
training/       adapter and distillation job planning
```

## Main Entry Points

- [`bootstrap.sh`](./bootstrap.sh): one-line installer entrypoint
- [`install_brain.py`](./install_brain.py): copies the scaffold into a target repo and resets machine-specific state
- [`scripts/run_audit.py`](./scripts/run_audit.py): primary orchestrator bootstrap and maintenance command

## Portable Design

This repository is meant to be copied into other repositories, not treated as a project-specific config dump. The installer resets machine-specific state such as:

- discovered capability lists
- discovery watch roots
- local audit history
- autopilot installation state
- route telemetry artifacts

That lets every target repository build its own environment-specific brain from a clean base.

## Typical Lifecycle

1. Install the scaffold into a target repo.
2. Run the first audit.
3. Let the brain discover and register capabilities.
4. Let startup rechecks detect new installs automatically.
5. Feed telemetry back into pruning, replay, and distillation workflows.

## Validation And CI

The project includes:

- JSON Schema validation for all portable registries and state files
- semantic validation across manifest, policies, and runtime contracts
- a GitHub Actions workflow that dry-runs the auditor safely for CI

## Repository

GitHub: [james96744/agenticswarm-brain](https://github.com/james96744/agenticswarm-brain)

## Status

This project is functional as a portable orchestration scaffold and installer. It is strongest today as:

- a repo bootstrapper
- a capability inventory system
- a policy-driven orchestration contract
- an automated maintenance backbone

The next layer beyond this is deeper runtime integration with real agent executors, model routers, and external tool backends.
