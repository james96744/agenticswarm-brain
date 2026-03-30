from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None

try:
    from brain_utils import (
        dump_json_stdout,
        dump_yaml_file,
        iter_repo_files,
        load_json_file,
        load_yaml_file,
        repo_root_from,
        safe_relpath,
    )
    from runtime_bridge import build_runtime_registry
    from sovereign_memory import ensure_state_files, update_product_context_from_discovery
except ModuleNotFoundError:
    from scripts.brain_utils import (
        dump_json_stdout,
        dump_yaml_file,
        iter_repo_files,
        load_json_file,
        load_yaml_file,
        repo_root_from,
        safe_relpath,
    )
    from scripts.runtime_bridge import build_runtime_registry
    from scripts.sovereign_memory import ensure_state_files, update_product_context_from_discovery


STACK_MARKERS = {
    "python": {"pyproject.toml", "requirements.txt", "requirements.in", "setup.py", "Pipfile"},
    "node": {"package.json", "pnpm-lock.yaml", "yarn.lock", "package-lock.json"},
    "rust": {"Cargo.toml"},
    "go": {"go.mod"},
    "java": {"pom.xml", "build.gradle", "settings.gradle"},
    "dotnet": {".sln", ".csproj"},
    "ruby": {"Gemfile"},
    "php": {"composer.json"},
    "docker": {"Dockerfile", "docker-compose.yml", "docker-compose.yaml"},
}

PROVIDER_ENV_MAP = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    "azure_openai": ("AZURE_OPENAI_API_KEY",),
    "cohere": ("COHERE_API_KEY",),
    "mistral": ("MISTRAL_API_KEY",),
}

RUNTIME_COMMANDS = {
    "ollama": {"provider": "ollama", "type": "local_runtime", "tier": "tier_1_worker"},
    "vllm": {"provider": "vllm", "type": "local_runtime", "tier": "tier_1_worker"},
}

DISCOVERY_EXCLUDED_PARTS = {
    "capabilities",
    "schemas",
    "telemetry",
    "memory",
    "training",
    "simulation",
    ".github",
}

GLOBAL_SKILL_ROOTS = (
    Path.home() / ".codex" / "skills",
    Path.home() / ".agents" / "skills",
)

GLOBAL_AGENT_ROOTS = (
    Path.home() / ".codex" / "agents",
    Path.home() / ".agents" / "agents",
    *GLOBAL_SKILL_ROOTS,
)

GLOBAL_PLUGIN_ROOTS = (
    Path.home() / ".codex" / "plugins",
    Path.home() / ".agents" / "plugins",
)

GLOBAL_CONFIG_ROOTS = (
    Path.home() / ".codex",
    Path.home() / ".agents",
    Path.home() / ".config",
    Path.home() / ".cursor",
    Path.home() / ".claude",
    Path.home() / "Library" / "Application Support" / "Claude",
    Path.home() / "Library" / "Application Support" / "Cursor",
    Path.home() / "Library" / "Application Support" / "Codex",
)

MODELS_CACHE_PATH = Path.home() / ".codex" / "models_cache.json"

MCP_PATTERNS = (
    "*mcp*.json",
    "*mcp*.yaml",
    "*mcp*.yml",
    "claude_desktop_config.json",
    "claude.json",
)

MCP_EXECUTABLE_HINTS = {
    "mcp",
    "modelcontextprotocol",
}

CLI_CANDIDATES = (
    "python",
    "python3",
    "pip",
    "pip3",
    "uv",
    "node",
    "npm",
    "npx",
    "pnpm",
    "yarn",
    "bun",
    "deno",
    "git",
    "gh",
    "rg",
    "jq",
    "yq",
    "make",
    "just",
    "docker",
    "docker-compose",
    "kubectl",
    "helm",
    "terraform",
    "tofu",
    "az",
    "ollama",
    "vllm",
    "codex",
    "claude",
    "aider",
    "pytest",
    "playwright",
    "nats",
    "grpcurl",
)

CLI_CATEGORY_MAP = {
    "python": "runtime",
    "python3": "runtime",
    "pip": "package_manager",
    "pip3": "package_manager",
    "uv": "package_manager",
    "node": "runtime",
    "npm": "package_manager",
    "npx": "package_manager",
    "pnpm": "package_manager",
    "yarn": "package_manager",
    "bun": "runtime",
    "deno": "runtime",
    "git": "vcs",
    "gh": "vcs",
    "rg": "search",
    "jq": "data",
    "yq": "data",
    "make": "build",
    "just": "build",
    "docker": "container",
    "docker-compose": "container",
    "kubectl": "orchestration",
    "helm": "orchestration",
    "terraform": "infra",
    "tofu": "infra",
    "az": "cloud",
    "ollama": "ai",
    "vllm": "ai",
    "codex": "ai",
    "claude": "ai",
    "aider": "ai",
    "pytest": "test",
    "playwright": "test",
    "nats": "messaging",
    "grpcurl": "network",
}

CLI_JSON_SUPPORT = {"gh", "jq", "yq", "docker", "kubectl", "az", "terraform", "tofu"}
CLI_DESTRUCTIVE_HINTS = {
    "git",
    "docker",
    "kubectl",
    "helm",
    "terraform",
    "tofu",
    "az",
}

LOCAL_EXECUTABLE_DIRS = (
    ".brain_integrations/bin",
    "node_modules/.bin",
    ".venv/bin",
    "venv/bin",
    "bin",
)

LOCAL_SCRIPT_DIRS = (
    "scripts",
    "tools",
)


def normalize_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "unknown"


def dedupe_by_key(items: list[dict], key: str) -> list[dict]:
    seen = {}
    for item in items:
        seen[item[key]] = item
    return list(seen.values())


def existing_paths(paths: tuple[Path, ...]) -> list[Path]:
    return [path for path in paths if path.exists()]


def scope_item(item: dict, scope: str, source: str) -> dict:
    scoped = dict(item)
    scoped["scope"] = scope
    scoped["source"] = source
    return scoped


def read_structured_file(path: Path):
    try:
        if path.suffix == ".json":
            return load_json_file(path)
        if path.suffix in {".yaml", ".yml"}:
            return load_yaml_file(path)
    except Exception:
        return {}
    return {}


def parse_toml_file(path: Path) -> dict:
    if tomllib is None or not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def detect_stacks(files: list[Path]) -> list[str]:
    stacks = set()
    names = {path.name for path in files}
    suffixes = {path.suffix for path in files}
    for stack, markers in STACK_MARKERS.items():
        if any(marker.startswith(".") and marker in suffixes for marker in markers):
            stacks.add(stack)
        if any(marker in names for marker in markers):
            stacks.add(stack)
    return sorted(stacks)


def detect_risk(files: list[Path]) -> str:
    joined = " ".join(path.as_posix().lower() for path in files)
    if any(token in joined for token in ("payment", "finance", "security", "legal", "medical", "deployment")):
        return "high"
    return "medium"


def should_skip_local_path(path: Path) -> bool:
    if ".brain_integrations" in path.parts:
        index = path.parts.index(".brain_integrations")
        if len(path.parts) > index + 1 and path.parts[index + 1] in {"repos", "venvs"}:
            return True
    return any(part in DISCOVERY_EXCLUDED_PARTS for part in path.parts)


def infer_cli_category(command: str) -> str:
    return CLI_CATEGORY_MAP.get(command, "general")


def infer_model_tier(model_name: str) -> str:
    lower = model_name.lower()
    if any(token in lower for token in ("embedding", "router", "bge", "e5")):
        return "tier_0_router"
    if any(token in lower for token in ("haiku", "critic", "review")):
        return "tier_2_critic"
    if any(token in lower for token in ("sonnet", "opus", "gpt-5", "gpt-4", "expert", "reason")):
        return "tier_3_expert"
    return "tier_1_worker"


def extract_mcp_entries(payload, path: Path, root: Path | None, scope: str, source: str) -> list[dict]:
    results = []
    if not isinstance(payload, dict):
        return results

    candidate_maps = []
    for key in ("mcpServers", "mcp_servers", "mcps"):
        value = payload.get(key)
        if isinstance(value, dict):
            candidate_maps.append(value)

    nested = payload.get("mcp")
    if isinstance(nested, dict):
        for key in ("servers", "mcpServers", "mcp_servers"):
            value = nested.get(key)
            if isinstance(value, dict):
                candidate_maps.append(value)

    for server_map in candidate_maps:
        for name, config in server_map.items():
            if not isinstance(config, dict):
                config = {}
            command = config.get("command")
            url = config.get("url")
            transport = config.get("transport") or ("stdio" if command else "http" if url else "unknown")
            entry = {
                "mcp_id": normalize_id(name),
                "enabled": config.get("enabled", True),
                "kind": "server_definition",
                "transport": transport,
                "path": safe_relpath(path, root) if root else str(path),
            }
            if command:
                entry["command"] = command
            if isinstance(config.get("args"), list):
                entry["args"] = config["args"]
            if url:
                entry["url"] = url
            if isinstance(config.get("capabilities"), list):
                entry["capabilities"] = config["capabilities"]
            results.append(scope_item(entry, scope, source))
    return results


def discover_local_agents(files: list[Path], root: Path) -> list[dict]:
    results = []
    for path in files:
        if should_skip_local_path(path):
            continue
        lower = path.name.lower()
        in_agents_dir = any(part.lower() == "agents" for part in path.parts)
        named_agent_file = lower in {"agents.md", "agent.md"}
        explicit_agent_name = path.stem.lower().endswith(("-agent", "_agent")) or path.stem.lower() == "agent"
        if path.suffix in {".md", ".yaml", ".yml", ".json"} and (named_agent_file or in_agents_dir or explicit_agent_name):
            results.append(
                scope_item(
                    {
                        "agent_id": normalize_id(path.stem),
                        "role": "repository_discovered",
                        "class": "specialist",
                        "enabled": True,
                        "path": safe_relpath(path, root),
                    },
                    "local",
                    "repository_discovered",
                )
            )
    return dedupe_by_key(results, "agent_id")


def discover_global_agents() -> list[dict]:
    results = []
    for agent_root in existing_paths(GLOBAL_AGENT_ROOTS):
        for path in agent_root.rglob("*"):
            if not path.is_file():
                continue
            lower = path.name.lower()
            if path.suffix not in {".yaml", ".yml", ".json", ".md"}:
                continue
            if not (lower in {"agents.md", "agent.md"} or "agent" in lower or any(part.lower() == "agents" for part in path.parts)):
                continue
            results.append(
                scope_item(
                    {
                        "agent_id": normalize_id(f"{path.parent.name}-{path.stem}"),
                        "role": "global_agent_config",
                        "class": "specialist",
                        "enabled": True,
                        "path": str(path),
                    },
                    "global",
                    "global_agent_config",
                )
            )
    return dedupe_by_key(results, "agent_id")


def discover_local_skills(files: list[Path], root: Path) -> list[dict]:
    results = []
    for path in files:
        if should_skip_local_path(path):
            continue
        if path.name != "SKILL.md":
            continue
        results.append(
            scope_item(
                {
                    "skill_id": normalize_id(path.parent.name),
                    "enabled": True,
                    "category": "repository_discovered",
                    "path": safe_relpath(path, root),
                },
                "local",
                "repository_local",
            )
        )
    return dedupe_by_key(results, "skill_id")


def discover_global_skills() -> list[dict]:
    results = []
    for skill_root in existing_paths(GLOBAL_SKILL_ROOTS):
        for path in skill_root.rglob("SKILL.md"):
            results.append(
                scope_item(
                    {
                        "skill_id": normalize_id(path.parent.name),
                        "enabled": True,
                        "category": "global_installed",
                        "path": str(path),
                    },
                    "global",
                    "global_skill",
                )
            )
    return dedupe_by_key(results, "skill_id")


def discover_local_plugins(files: list[Path], root: Path) -> list[dict]:
    results = []
    for path in files:
        if should_skip_local_path(path):
            continue
        if path.name != "plugin.json" and ".codex-plugin" not in path.as_posix():
            continue
        plugin_root = path.parent.parent if path.name == "plugin.json" and path.parent.name == ".codex-plugin" else path.parent
        payload = read_structured_file(path)
        plugin_id = payload.get("id") if isinstance(payload, dict) else None
        results.append(
            scope_item(
                {
                    "plugin_id": normalize_id(plugin_id or plugin_root.name),
                    "type": "plugin",
                    "enabled": True,
                    "category": "repository_discovered",
                    "path": safe_relpath(path, root),
                },
                "local",
                "repository_discovered",
            )
        )
    return dedupe_by_key(results, "plugin_id")


def discover_global_plugins() -> list[dict]:
    results = []
    for plugin_root in existing_paths(GLOBAL_PLUGIN_ROOTS):
        for path in plugin_root.rglob("plugin.json"):
            payload = read_structured_file(path)
            plugin_id = payload.get("id") if isinstance(payload, dict) else None
            results.append(
                scope_item(
                    {
                        "plugin_id": normalize_id(plugin_id or path.parent.name),
                        "type": "plugin",
                        "enabled": True,
                        "category": "global_installed",
                        "path": str(path),
                    },
                    "global",
                    "global_plugin",
                )
            )
    return dedupe_by_key(results, "plugin_id")


def discover_local_mcp(files: list[Path], root: Path) -> list[dict]:
    results = []
    for path in files:
        if should_skip_local_path(path):
            continue
        lower_path = path.as_posix().lower()
        is_candidate = (
            path.suffix in {".json", ".yaml", ".yml"} and "mcp" in lower_path
        ) or path.name in {"claude_desktop_config.json", "claude.json"}
        if not is_candidate:
            continue
        payload = read_structured_file(path)
        extracted = extract_mcp_entries(payload, path, root, "local", "repository_discovered")
        if extracted:
            results.extend(extracted)
            continue
        results.append(
            scope_item(
                {
                    "mcp_id": normalize_id(path.stem),
                    "enabled": True,
                    "kind": "config_file",
                    "path": safe_relpath(path, root),
                },
                "local",
                "repository_discovered",
            )
        )

    for relative_dir in LOCAL_EXECUTABLE_DIRS + LOCAL_SCRIPT_DIRS:
        cli_dir = root / relative_dir
        if not cli_dir.exists() or not cli_dir.is_dir():
            continue
        for child in cli_dir.iterdir():
            if "mcp" not in child.name.lower():
                continue
            if child.is_file() and os.access(child, os.X_OK):
                results.append(
                    scope_item(
                        {
                            "mcp_id": normalize_id(child.stem),
                            "enabled": True,
                            "kind": "executable_wrapper",
                            "command": child.name,
                            "path": safe_relpath(child, root),
                        },
                        "local",
                        "repository_executable",
                    )
                )
    return dedupe_by_key(results, "mcp_id")


def discover_global_mcp() -> list[dict]:
    results = []
    for config_root in existing_paths(GLOBAL_CONFIG_ROOTS):
        for pattern in MCP_PATTERNS:
            for path in config_root.rglob(pattern):
                payload = read_structured_file(path)
                extracted = extract_mcp_entries(payload, path, None, "global", "global_mcp_config")
                if extracted:
                    results.extend(extracted)
                    continue
                results.append(
                    scope_item(
                        {
                            "mcp_id": normalize_id(path.stem),
                            "enabled": True,
                            "kind": "config_file",
                            "path": str(path),
                        },
                        "global",
                        "global_mcp_config",
                    )
                )

    for path_dir in {Path(item) for item in os.get_exec_path() if item}:
        if not path_dir.exists() or not path_dir.is_dir():
            continue
        for child in path_dir.iterdir():
            name = child.name.lower()
            if not child.is_file() or not os.access(child, os.X_OK):
                continue
            if "mcp" not in name and not any(hint in name for hint in MCP_EXECUTABLE_HINTS):
                continue
            results.append(
                scope_item(
                    {
                        "mcp_id": normalize_id(child.stem),
                        "enabled": True,
                        "kind": "executable_wrapper",
                        "command": child.name,
                        "path": str(child),
                    },
                    "global",
                    "global_mcp_executable",
                )
            )
    return dedupe_by_key(results, "mcp_id")


def discover_pyproject_scripts(root: Path) -> list[dict]:
    results = []
    pyproject = parse_toml_file(root / "pyproject.toml")
    project = pyproject.get("project", {}) if isinstance(pyproject, dict) else {}
    tool = pyproject.get("tool", {}) if isinstance(pyproject, dict) else {}
    poetry = tool.get("poetry", {}) if isinstance(tool, dict) else {}

    for name, target in (project.get("scripts", {}) if isinstance(project.get("scripts", {}), dict) else {}).items():
        results.append(
            {
                "cli_id": normalize_id(name),
                "command": name,
                "enabled": True,
                "category": "project_script",
                "kind": "python_entrypoint",
                "runtime": "python",
                "path": "pyproject.toml",
                "entrypoint": target,
            }
        )

    for name, target in (poetry.get("scripts", {}) if isinstance(poetry.get("scripts", {}), dict) else {}).items():
        results.append(
            {
                "cli_id": normalize_id(name),
                "command": name,
                "enabled": True,
                "category": "project_script",
                "kind": "python_entrypoint",
                "runtime": "python",
                "path": "pyproject.toml",
                "entrypoint": target,
            }
        )
    return results


def discover_package_json_scripts(root: Path) -> list[dict]:
    package_json = root / "package.json"
    if not package_json.exists():
        return []
    payload = read_structured_file(package_json)
    if not isinstance(payload, dict):
        return []
    results = []
    scripts = payload.get("scripts", {})
    if isinstance(scripts, dict):
        for name, command in scripts.items():
            results.append(
                {
                    "cli_id": normalize_id(f"npm-script-{name}"),
                    "command": f"npm run {name}",
                    "enabled": True,
                    "category": "project_script",
                    "kind": "package_script",
                    "runtime": "node",
                    "path": "package.json",
                    "script_name": name,
                    "script_body": command,
                    "destructive": any(token in str(command).lower() for token in ("deploy", "destroy", "delete", "remove")),
                    "supports_json_output": False,
                }
            )
    return results


def discover_local_cli(root: Path) -> list[dict]:
    results = []

    for relative_dir in LOCAL_EXECUTABLE_DIRS:
        cli_dir = root / relative_dir
        if not cli_dir.exists() or not cli_dir.is_dir():
            continue
        for child in cli_dir.iterdir():
            if not child.is_file() or not os.access(child, os.X_OK):
                continue
            results.append(
                scope_item(
                    {
                        "cli_id": normalize_id(child.name),
                        "command": child.name,
                        "enabled": True,
                        "category": infer_cli_category(child.name),
                        "kind": "local_binary",
                        "runtime": "unknown",
                        "destructive": child.name in CLI_DESTRUCTIVE_HINTS,
                        "supports_json_output": child.name in CLI_JSON_SUPPORT,
                        "path": safe_relpath(child, root),
                    },
                    "local",
                    "repository_binary",
                )
            )

    for relative_dir in LOCAL_SCRIPT_DIRS:
        script_dir = root / relative_dir
        if not script_dir.exists() or not script_dir.is_dir():
            continue
        for child in script_dir.iterdir():
            if child.is_dir():
                continue
            if child.suffix not in {".py", ".sh"} and not os.access(child, os.X_OK):
                continue
            command_name = child.stem if child.suffix in {".py", ".sh"} else child.name
            runtime = "python" if child.suffix == ".py" else "shell" if child.suffix == ".sh" else "unknown"
            results.append(
                scope_item(
                    {
                        "cli_id": normalize_id(command_name),
                        "command": command_name,
                        "enabled": True,
                        "category": "project_script",
                        "kind": "repository_script",
                        "runtime": runtime,
                        "destructive": any(token in child.name.lower() for token in ("deploy", "destroy", "delete", "remove")),
                        "supports_json_output": False,
                        "path": safe_relpath(child, root),
                    },
                    "local",
                    "repository_script",
                )
            )

    for item in discover_package_json_scripts(root):
        results.append(scope_item(item, "local", "package_json"))
    for item in discover_pyproject_scripts(root):
        results.append(scope_item(item, "local", "pyproject"))

    return dedupe_by_key(results, "cli_id")


def discover_global_cli() -> list[dict]:
    results = []
    for command in CLI_CANDIDATES:
        resolved = shutil.which(command)
        if not resolved:
            continue
        results.append(
            scope_item(
                {
                    "cli_id": normalize_id(command),
                    "command": command,
                    "enabled": True,
                    "category": infer_cli_category(command),
                    "kind": "global_binary",
                    "runtime": "unknown",
                    "destructive": command in CLI_DESTRUCTIVE_HINTS,
                    "supports_json_output": command in CLI_JSON_SUPPORT,
                    "path": resolved,
                },
                "global",
                "path_lookup",
            )
        )
    return dedupe_by_key(results, "cli_id")


def discover_models() -> list[dict]:
    results = []
    for provider, keys in PROVIDER_ENV_MAP.items():
        if any(os.environ.get(key) for key in keys):
            results.append(
                scope_item(
                    {
                        "model_id": f"{provider}-auto",
                        "provider": provider,
                        "type": "llm_provider",
                        "tier": "tier_1_worker",
                        "enabled": True,
                        "status": "available",
                    },
                    "global",
                    "environment",
                )
            )
    for command, metadata in RUNTIME_COMMANDS.items():
        if shutil.which(command):
            results.append(
                scope_item(
                    {
                        "model_id": f"{command}-runtime",
                        "provider": metadata["provider"],
                        "type": metadata["type"],
                        "tier": metadata["tier"],
                        "enabled": True,
                        "status": "available",
                    },
                    "global",
                    "runtime",
                )
            )
    if MODELS_CACHE_PATH.exists():
        try:
            cache = load_json_file(MODELS_CACHE_PATH)
        except Exception:
            cache = {}
        for model in cache.get("models", []):
            model_id = model.get("slug", model.get("display_name", "unknown-model"))
            results.append(
                scope_item(
                    {
                        "model_id": model_id,
                        "provider": model.get("provider", "codex_cache"),
                        "type": "cached_catalog_model",
                        "tier": infer_model_tier(model_id),
                        "enabled": True,
                        "status": "catalogued",
                        "display_name": model.get("display_name"),
                        "supported_in_api": model.get("supported_in_api"),
                    },
                    "global",
                    "global_model_cache",
                )
            )
    return dedupe_by_key(results, "model_id")


def counts_for(payload: dict[str, list[dict]]) -> dict[str, int]:
    return {key: len(value) for key, value in payload.items()}


def build_watch_roots(root: Path, discovery_items: dict[str, list[dict]]) -> list[str]:
    watch_roots: set[Path] = {root}

    for candidate in existing_paths(GLOBAL_SKILL_ROOTS + GLOBAL_AGENT_ROOTS + GLOBAL_PLUGIN_ROOTS + GLOBAL_CONFIG_ROOTS):
        watch_roots.add(candidate)

    for relative_dir in LOCAL_EXECUTABLE_DIRS + LOCAL_SCRIPT_DIRS:
        candidate = root / relative_dir
        if candidate.exists():
            watch_roots.add(candidate)

    for path_entry in discovery_items.get("agents", []):
        path_value = path_entry.get("path")
        if path_entry.get("scope") == "local" and path_value:
            watch_roots.add((root / path_value).parent)
        elif path_value:
            watch_roots.add(Path(path_value).parent)

    for category in ("skills", "plugins", "mcp_entries", "cli_entries"):
        for item in discovery_items.get(category, []):
            path_value = item.get("path")
            if not path_value:
                continue
            candidate = (root / path_value) if item.get("scope") == "local" else Path(path_value)
            watch_roots.add(candidate.parent if candidate.is_file() or "." in candidate.name else candidate)

    for path_dir in os.get_exec_path():
        if path_dir:
            watch_roots.add(Path(path_dir))

    return sorted(str(path.resolve()) for path in watch_roots if path.exists())


def collect_discovery(root: Path) -> dict:
    repo_files = list(iter_repo_files(root))

    local = {
        "agents": discover_local_agents(repo_files, root),
        "skills": discover_local_skills(repo_files, root),
        "plugins": discover_local_plugins(repo_files, root),
        "mcp_entries": discover_local_mcp(repo_files, root),
        "cli_entries": discover_local_cli(root),
        "models": [],
    }
    global_items = {
        "agents": discover_global_agents(),
        "skills": discover_global_skills(),
        "plugins": discover_global_plugins(),
        "mcp_entries": discover_global_mcp(),
        "cli_entries": discover_global_cli(),
        "models": discover_models(),
    }
    combined = {
        "agents": dedupe_by_key(global_items["agents"] + local["agents"], "agent_id"),
        "skills": dedupe_by_key(global_items["skills"] + local["skills"], "skill_id"),
        "plugins": dedupe_by_key(global_items["plugins"] + local["plugins"], "plugin_id"),
        "mcp_entries": dedupe_by_key(global_items["mcp_entries"] + local["mcp_entries"], "mcp_id"),
        "cli_entries": dedupe_by_key(global_items["cli_entries"] + local["cli_entries"], "cli_id"),
        "models": dedupe_by_key(global_items["models"], "model_id"),
    }

    return {
        "repository": {
            "path": str(root),
            "name": root.name,
            "stacks": detect_stacks(repo_files),
            "risk_level": detect_risk(repo_files),
            "file_count": len(repo_files),
        },
        "local": {
            "counts": counts_for(local),
            "items": local,
        },
        "global": {
            "counts": counts_for(global_items),
            "items": global_items,
        },
        "combined": {
            "counts": counts_for(combined),
            "items": combined,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "watch_roots": build_watch_roots(root, combined),
    }


def update_brain_manifest(root: Path, discovery: dict) -> None:
    path = root / "brain.schema.yaml"
    data = load_yaml_file(path)
    manifest = data.setdefault("brain_manifest", {})
    profile = manifest.setdefault("repository_profile", {})
    profile["name"] = discovery["repository"]["name"]
    profile["stack"] = discovery["repository"]["stacks"]
    profile["risk_level"] = discovery["repository"]["risk_level"]
    manifest["discovery_summary"] = {
        "local_counts": discovery["local"]["counts"],
        "global_counts": discovery["global"]["counts"],
        "combined_counts": discovery["combined"]["counts"],
        "generated_at": discovery["generated_at"],
    }
    dump_yaml_file(path, data)


def update_registry(root: Path, relative_path: str, key: str, items: list[dict]) -> None:
    path = root / relative_path
    data = load_yaml_file(path)
    data[key] = items
    data["last_updated"] = datetime.now(timezone.utc).date().isoformat()
    dump_yaml_file(path, data)


def apply_discovery(root: Path, discovery: dict) -> None:
    ensure_state_files(root)
    update_brain_manifest(root, discovery)
    update_registry(root, "capabilities/agents.yaml", "agents", discovery["combined"]["items"]["agents"])
    update_registry(root, "capabilities/skills.yaml", "skills", discovery["combined"]["items"]["skills"])
    update_registry(root, "capabilities/plugins.yaml", "plugins", discovery["combined"]["items"]["plugins"])
    update_registry(root, "capabilities/mcp.yaml", "mcp_entries", discovery["combined"]["items"]["mcp_entries"])
    update_registry(root, "capabilities/cli.yaml", "cli_entries", discovery["combined"]["items"]["cli_entries"])
    update_registry(root, "capabilities/models.yaml", "models", discovery["combined"]["items"]["models"])
    build_runtime_registry(root, write=True)
    update_product_context_from_discovery(root, discovery)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap portable brain registries from repository and global discovery.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    discovery = collect_discovery(root)

    if not args.dry_run:
        apply_discovery(root, discovery)

    dump_json_stdout(discovery)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
