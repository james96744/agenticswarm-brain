from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

try:
    from brain_utils import dump_json_stdout, dump_yaml_file, file_lock, load_yaml_file, repo_root_from
    from bootstrap_brain import apply_discovery, collect_discovery
except ModuleNotFoundError:
    from scripts.brain_utils import dump_json_stdout, dump_yaml_file, file_lock, load_yaml_file, repo_root_from
    from scripts.bootstrap_brain import apply_discovery, collect_discovery


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_profiles(root: Path) -> dict[str, dict]:
    payload = load_yaml_file(root / "capabilities/brain_network_install_profiles.yaml")
    return {
        item.get("integration_id"): item
        for item in payload.get("profiles", [])
        if item.get("integration_id")
    }


def load_registry(root: Path) -> dict[str, dict]:
    payload = load_yaml_file(root / "capabilities/brain_network.yaml")
    return {
        item.get("integration_id"): item
        for item in payload.get("integrations", [])
        if item.get("integration_id")
    }


def load_policy_wave_categories(root: Path, wave: int) -> list[str]:
    policies = load_yaml_file(root / "orchestrator/policies.yaml")
    waves = policies.get("brain_network_policy", {}).get("install_waves", {})
    return list(waves.get(f"wave_{wave}", []))


def load_install_state(root: Path) -> dict:
    return load_yaml_file(root / "telemetry/brain_network_installs.yaml")


def upsert_install_record(root: Path, record: dict) -> None:
    path = root / "telemetry/brain_network_installs.yaml"
    with file_lock(path.with_suffix(path.suffix + ".lock")):
        payload = load_yaml_file(path)
        installs = payload.setdefault("installs", [])
        installs[:] = [item for item in installs if item.get("integration_id") != record.get("integration_id")]
        installs.append(record)
        payload["last_updated"] = datetime.now(timezone.utc).date().isoformat()
        dump_yaml_file(path, payload)


def append_note(root: Path, benchmark: dict) -> None:
    path = root / "telemetry/brain_network_installs.yaml"
    with file_lock(path.with_suffix(path.suffix + ".lock")):
        payload = load_yaml_file(path)
        payload.setdefault("benchmarks", []).append(benchmark)
        payload["last_updated"] = datetime.now(timezone.utc).date().isoformat()
        dump_yaml_file(path, payload)


def run_command(command: list[str], *, cwd: Path | None = None, dry_run: bool = False) -> dict:
    if dry_run:
        return {"status": "dry_run", "command": command, "cwd": str(cwd) if cwd else None, "exit_code": 0, "stdout": "", "stderr": ""}
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "status": "success" if completed.returncode == 0 else "failed",
        "command": command,
        "cwd": str(cwd) if cwd else None,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def ensure_dirs(root: Path) -> dict[str, Path]:
    install_root = root / ".brain_integrations"
    paths = {
        "root": install_root,
        "repos": install_root / "repos",
        "venvs": install_root / "venvs",
        "bin": install_root / "bin",
        "mcp": install_root / "mcp",
        "npm": install_root / "npm",
        "skills": install_root / "skills",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def clone_repo(repo_url: str, dest: Path, *, dry_run: bool) -> dict:
    if dest.exists():
        return run_command(["git", "-C", str(dest), "pull", "--ff-only"], dry_run=dry_run)
    return run_command(["git", "clone", "--depth", "1", repo_url, str(dest)], dry_run=dry_run)


def make_executable(path: Path, *, dry_run: bool) -> None:
    if dry_run:
        return
    mode = path.stat().st_mode
    path.chmod(mode | 0o111)


def write_wrapper(path: Path, content: str, *, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    make_executable(path, dry_run=False)


def write_mcp_config(path: Path, server_name: str, command: str, args: list[str], *, dry_run: bool) -> None:
    payload = {
        "mcpServers": {
            server_name: {
                "command": command,
                "args": args,
            }
        }
    }
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_skill_wrapper(path: Path, content: str, *, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def binary_relpath(root: Path, path: Path) -> str:
    return f"./{path.relative_to(root)}"


def install_codebase_memory(root: Path, integration: dict, paths: dict[str, Path], *, dry_run: bool) -> dict:
    repo_dir = paths["repos"] / "codebase-memory-mcp"
    clone = clone_repo(integration["repo_url"], repo_dir, dry_run=dry_run)
    install = run_command(
        ["bash", str(repo_dir / "install.sh"), "--dir", str(paths["bin"]), "--skip-config"],
        cwd=repo_dir,
        dry_run=dry_run,
    )
    config_path = paths["mcp"] / "codebase-memory-mcp.mcp.json"
    write_mcp_config(
        config_path,
        "codebase-memory-mcp",
        binary_relpath(root, paths["bin"] / "codebase-memory-mcp"),
        [],
        dry_run=dry_run,
    )
    return {
        "status": "activated" if install["status"] in {"success", "dry_run"} else "blocked",
        "repo_path": str(repo_dir),
        "wrapper_paths": [str(config_path)],
        "steps": [clone, install],
    }


def install_context_portal(root: Path, integration: dict, paths: dict[str, Path], *, dry_run: bool) -> dict:
    repo_dir = paths["repos"] / "context-portal"
    venv_dir = paths["venvs"] / "context-portal"
    wrapper_path = paths["bin"] / "context-portal-mcp"
    config_path = paths["mcp"] / "context-portal.mcp.json"
    steps = [
        clone_repo(integration["repo_url"], repo_dir, dry_run=dry_run),
        run_command(["uv", "venv", str(venv_dir)], dry_run=dry_run),
        run_command(["uv", "pip", "install", "--python", str(venv_dir / "bin" / "python"), "-e", str(repo_dir)], dry_run=dry_run),
    ]
    wrapper = f"""#!/usr/bin/env bash
set -euo pipefail
exec "{venv_dir / 'bin' / 'conport-mcp'}" --mode stdio --workspace-search-start .
"""
    write_wrapper(wrapper_path, wrapper, dry_run=dry_run)
    write_mcp_config(config_path, "context-portal", binary_relpath(root, wrapper_path), [], dry_run=dry_run)
    ok = all(step["status"] in {"success", "dry_run"} for step in steps)
    return {
        "status": "activated" if ok else "blocked",
        "repo_path": str(repo_dir),
        "wrapper_paths": [str(wrapper_path), str(config_path)],
        "steps": steps,
    }


def install_nocturne(root: Path, integration: dict, paths: dict[str, Path], *, dry_run: bool) -> dict:
    repo_dir = paths["repos"] / "nocturne_memory"
    venv_dir = paths["venvs"] / "nocturne-memory"
    wrapper_path = paths["bin"] / "nocturne-memory-mcp"
    config_path = paths["mcp"] / "nocturne-memory.mcp.json"
    steps = [
        clone_repo(integration["repo_url"], repo_dir, dry_run=dry_run),
        run_command(["uv", "venv", str(venv_dir)], dry_run=dry_run),
        run_command(
            ["uv", "pip", "install", "--python", str(venv_dir / "bin" / "python"), "-r", str(repo_dir / "backend" / "requirements.txt")],
            dry_run=dry_run,
        ),
    ]
    wrapper = f"""#!/usr/bin/env bash
set -euo pipefail
exec "{venv_dir / 'bin' / 'python'}" "{repo_dir / 'backend' / 'mcp_server.py'}"
"""
    write_wrapper(wrapper_path, wrapper, dry_run=dry_run)
    write_mcp_config(config_path, "nocturne-memory", binary_relpath(root, wrapper_path), [], dry_run=dry_run)
    ok = all(step["status"] in {"success", "dry_run"} for step in steps)
    return {
        "status": "activated" if ok else "blocked",
        "repo_path": str(repo_dir),
        "wrapper_paths": [str(wrapper_path), str(config_path)],
        "steps": steps,
    }


def install_memorix(root: Path, integration: dict, paths: dict[str, Path], *, dry_run: bool) -> dict:
    repo_dir = paths["repos"] / "memorix"
    wrapper_path = paths["bin"] / "memorix-mcp"
    config_path = paths["mcp"] / "memorix.mcp.json"
    steps = [
        clone_repo(integration["repo_url"], repo_dir, dry_run=dry_run),
        run_command(["npm", "install"], cwd=repo_dir, dry_run=dry_run),
        run_command(["npm", "run", "build"], cwd=repo_dir, dry_run=dry_run),
    ]
    wrapper = f"""#!/usr/bin/env bash
set -euo pipefail
exec node "{repo_dir / 'dist' / 'cli' / 'index.js'}" serve
"""
    write_wrapper(wrapper_path, wrapper, dry_run=dry_run)
    write_mcp_config(config_path, "memorix", binary_relpath(root, wrapper_path), [], dry_run=dry_run)
    ok = all(step["status"] in {"success", "dry_run"} for step in steps)
    return {
        "status": "activated" if ok else "blocked",
        "repo_path": str(repo_dir),
        "wrapper_paths": [str(wrapper_path), str(config_path)],
        "steps": steps,
    }


def install_context_forge(root: Path, integration: dict, paths: dict[str, Path], *, dry_run: bool) -> dict:
    repo_dir = paths["repos"] / "mcp-context-forge"
    venv_dir = paths["venvs"] / "mcp-context-forge"
    wrapper_path = paths["bin"] / "mcp-context-forge-service"
    steps = [
        clone_repo(integration["repo_url"], repo_dir, dry_run=dry_run),
        run_command(["uv", "venv", str(venv_dir)], dry_run=dry_run),
        run_command(["uv", "pip", "install", "--python", str(venv_dir / "bin" / "python"), "-e", str(repo_dir)], dry_run=dry_run),
    ]
    wrapper = f"""#!/usr/bin/env bash
set -euo pipefail
exec "{venv_dir / 'bin' / 'mcpgateway'}" --host 127.0.0.1 --port 4444
"""
    write_wrapper(wrapper_path, wrapper, dry_run=dry_run)
    ok = all(step["status"] in {"success", "dry_run"} for step in steps)
    return {
        "status": "installed_assets_only" if ok else "blocked",
        "repo_path": str(repo_dir),
        "wrapper_paths": [str(wrapper_path)],
        "steps": steps,
        "blocked_reason": None if ok else "install_failed",
        "activation_note": "Gateway service installed locally but not auto-activated as an MCP endpoint.",
    }


def install_claude_code_skills(root: Path, integration: dict, paths: dict[str, Path], *, dry_run: bool) -> dict:
    repo_dir = paths["repos"] / "claude-code-skills"
    npm_prefix = paths["npm"] / "claude-code-skills"
    hex_line_wrapper = paths["bin"] / "hex-line-mcp"
    hex_graph_wrapper = paths["bin"] / "hex-graph-mcp"
    hex_line_config = paths["mcp"] / "hex-line.mcp.json"
    hex_graph_config = paths["mcp"] / "hex-graph.mcp.json"
    skill_path = paths["skills"] / "claude-code-skills" / "SKILL.md"
    steps = [
        clone_repo(integration["repo_url"], repo_dir, dry_run=dry_run),
        run_command(
            [
                "npm",
                "install",
                "--prefix",
                str(npm_prefix),
                "@levnikolaevich/hex-line-mcp",
                "@levnikolaevich/hex-graph-mcp",
            ],
            dry_run=dry_run,
        ),
    ]
    write_wrapper(
        hex_line_wrapper,
        f"""#!/usr/bin/env bash
set -euo pipefail
exec node "{npm_prefix / 'node_modules' / '@levnikolaevich' / 'hex-line-mcp' / 'dist' / 'server.mjs'}"
""",
        dry_run=dry_run,
    )
    write_wrapper(
        hex_graph_wrapper,
        f"""#!/usr/bin/env bash
set -euo pipefail
exec node "{npm_prefix / 'node_modules' / '@levnikolaevich' / 'hex-graph-mcp' / 'dist' / 'server.mjs'}"
""",
        dry_run=dry_run,
    )
    write_mcp_config(hex_line_config, "hex-line", binary_relpath(root, hex_line_wrapper), [], dry_run=dry_run)
    write_mcp_config(hex_graph_config, "hex-graph", binary_relpath(root, hex_graph_wrapper), [], dry_run=dry_run)
    write_skill_wrapper(
        skill_path,
        f"""
# Claude Code Skills Integration

Use this installed overlay when the task benefits from hash-verified editing, code-graph retrieval, or tighter workflow guardrails.

Installed repo: {repo_dir}
Installed MCP servers:
- hex-line: hash-verified editing and safer file mutation
- hex-graph: layered code graph and architecture/code-intelligence retrieval

Prefer these servers when the brain needs higher-confidence edits or code-graph context with lower stale-file risk.
""",
        dry_run=dry_run,
    )
    ok = all(step["status"] in {"success", "dry_run"} for step in steps)
    return {
        "status": "activated" if ok else "blocked",
        "repo_path": str(repo_dir),
        "wrapper_paths": [
            str(hex_line_wrapper),
            str(hex_graph_wrapper),
            str(hex_line_config),
            str(hex_graph_config),
            str(skill_path),
        ],
        "steps": steps,
    }


def install_continuous_claude(root: Path, integration: dict, paths: dict[str, Path], *, dry_run: bool) -> dict:
    repo_dir = paths["repos"] / "continuous-claude-v3"
    skill_path = paths["skills"] / "continuous-claude-v3" / "SKILL.md"
    steps = [clone_repo(integration["repo_url"], repo_dir, dry_run=dry_run)]
    write_skill_wrapper(
        skill_path,
        f"""
# Continuous Claude v3 Continuity Overlay

Use this overlay when the brain needs longer-session continuity, handoff discipline, or session-compaction recovery patterns.

Installed repo: {repo_dir}
Relevant upstream assets:
- opc/scripts/benchmark_tokens.py
- opc/scripts/observe_agents.py
- opc/scripts/recall_temporal_facts.py
- opc/scripts/setup/wizard.py

Treat this as a continuity and workflow reference layer. It is installed locally for reuse, but not auto-activated as a background system inside this brain.
""",
        dry_run=dry_run,
    )
    ok = all(step["status"] in {"success", "dry_run"} for step in steps)
    return {
        "status": "installed_assets_only" if ok else "blocked",
        "repo_path": str(repo_dir),
        "wrapper_paths": [str(skill_path)],
        "steps": steps,
        "blocked_reason": None if ok else "install_failed",
        "activation_note": "Continuity overlay installed locally as a skill/reference layer without enabling its full daemon stack.",
    }


def blocked_record(integration_id: str, reason: str, profile: dict) -> dict:
    return {
        "integration_id": integration_id,
        "status": "blocked",
        "install_tier": profile.get("install_tier"),
        "installed_at": utc_now(),
        "activated_at": None,
        "blocked_reason": reason,
        "wrapper_paths": [],
        "steps": [],
    }


INSTALLERS = {
    "codebase-memory-mcp": install_codebase_memory,
    "context-portal": install_context_portal,
    "nocturne-memory": install_nocturne,
    "memorix": install_memorix,
    "continuous-claude-v3": install_continuous_claude,
    "claude-code-skills": install_claude_code_skills,
    "mcp-context-forge": install_context_forge,
}


def install_integration(root: Path, integration: dict, profile: dict, paths: dict[str, Path], *, dry_run: bool) -> dict:
    integration_id = integration["integration_id"]
    policies = load_yaml_file(root / "orchestrator/policies.yaml")
    active_tier = policies.get("packaging_profile", {}).get("active_tier", "community")
    allowed_tiers = set(integration.get("recommended_distribution_tiers", []))
    if allowed_tiers and active_tier not in allowed_tiers:
        return blocked_record(integration_id, f"packaging_tier_not_allowed:{active_tier}", profile)
    commands = set(profile.get("requirements", {}).get("commands", []))
    if "docker" in commands and not shutil_which("docker"):
        return blocked_record(integration_id, "missing_required_command:docker", profile)
    if "git-lfs" in commands and not shutil_which("git-lfs"):
        return blocked_record(integration_id, "missing_required_command:git-lfs", profile)
    if "uv" in commands and not shutil_which("uv"):
        return blocked_record(integration_id, "missing_required_command:uv", profile)
    if "npm" in commands and not shutil_which("npm"):
        return blocked_record(integration_id, "missing_required_command:npm", profile)
    installer = INSTALLERS.get(integration_id)
    if installer is None:
        return blocked_record(integration_id, "no_local_installer_implemented", profile)
    result = installer(root, integration, paths, dry_run=dry_run)
    return {
        "integration_id": integration_id,
        "status": result.get("status", "blocked"),
        "install_tier": profile.get("install_tier"),
        "installed_at": utc_now(),
        "activated_at": utc_now() if result.get("status") == "activated" else None,
        "blocked_reason": result.get("blocked_reason"),
        "repo_path": result.get("repo_path"),
        "wrapper_paths": result.get("wrapper_paths", []),
        "steps": result.get("steps", []),
        "activation_note": result.get("activation_note"),
    }


def shutil_which(command: str) -> str | None:
    return __import__("shutil").which(command)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install curated brain-network integrations into a repo-local runtime footprint.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--wave", type=int, default=1)
    parser.add_argument("--integration-id", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-discovery-refresh", action="store_true")
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    registry = load_registry(root)
    profiles = load_profiles(root)
    paths = ensure_dirs(root)

    if args.integration_id:
        selected_ids = [item for item in args.integration_id if item in registry]
    else:
        categories = set(load_policy_wave_categories(root, args.wave))
        selected_ids = [
            integration_id
            for integration_id, integration in registry.items()
            if integration.get("category") in categories
        ]

    results = []
    for integration_id in selected_ids:
        integration = registry[integration_id]
        profile = profiles.get(integration_id, {})
        record = install_integration(root, integration, profile, paths, dry_run=args.dry_run)
        upsert_install_record(root, record) if not args.dry_run else None
        results.append(record)

    discovery_refreshed = False
    if not args.dry_run and not args.skip_discovery_refresh:
        discovery = collect_discovery(root)
        apply_discovery(root, discovery)
        discovery_refreshed = True

    payload = {
        "status": "success",
        "selected_integrations": selected_ids,
        "results": results,
        "discovery_refreshed": discovery_refreshed,
    }
    dump_json_stdout(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
