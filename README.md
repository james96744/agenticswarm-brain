# AgenticSwarm Brain

Portable repo-aware orchestration scaffold for multi-agent LLM workflows.

It is designed to be dropped into any repository, inspect that repository plus the globally installed agent/skill/MCP/CLI/model surface, then keep itself updated through the auditor autopilot.

## Install Into Another Repo

One-liner bootstrap:

```bash
curl -fsSL https://raw.githubusercontent.com/james96744/agenticswarm-brain/main/bootstrap.sh | bash
```

Install into the current directory:

```bash
curl -fsSL https://raw.githubusercontent.com/james96744/agenticswarm-brain/main/bootstrap.sh | bash -s -- .
```

Install into a specific repo path:

```bash
curl -fsSL https://raw.githubusercontent.com/james96744/agenticswarm-brain/main/bootstrap.sh | bash -s -- /path/to/your/repo
```

Manual install from a local clone:

```bash
python3 install_brain.py --target /path/to/your/repo
```

Then in the target repo:

```bash
python3 -m venv .venv
./.venv/bin/pip install pyyaml jsonschema
./.venv/bin/python scripts/run_audit.py --repo-root .
```

That first real audit bootstraps the brain, populates the capability registries, validates the system, runs maintenance, and installs background startup rechecks on supported platforms.

## GitHub Publish

This directory can be published as its own repository. The remaining blocker on this machine is GitHub authentication for `gh`.

Once authenticated:

```bash
gh auth login
gh repo create agenticswarm-brain --source=. --public --push
```
