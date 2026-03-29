from __future__ import annotations

from pathlib import Path
import subprocess
import sys

try:
    from brain_utils import load_yaml_file, repo_root_from
except ModuleNotFoundError:
    from scripts.brain_utils import load_yaml_file, repo_root_from


def load_anatomy_registry(root: Path) -> dict:
    payload = load_yaml_file(root / "orchestrator" / "anatomy_registry.yaml")
    return payload.get("anatomy_modules", {})


def usage(anatomy_key: str, entry: dict) -> str:
    actions = entry.get("actions", {})
    lines = [
        f"{entry.get('label', anatomy_key)} wrapper",
        entry.get("description", ""),
        "",
        "Available actions:",
    ]
    for action, config in sorted(actions.items()):
        lines.append(f"  {action:<10} {config.get('description', '').strip()}")
    lines.append("")
    lines.append(f"Example: python scripts/{anatomy_key}.py {next(iter(actions), 'action')} --repo-root . --dry-run")
    return "\n".join(lines).strip()


def dispatch(anatomy_key: str, argv: list[str] | None = None) -> int:
    root = repo_root_from(None)
    registry = load_anatomy_registry(root)
    entry = registry.get(anatomy_key)
    if entry is None:
        print(f"Unknown anatomy key `{anatomy_key}` in orchestrator/anatomy_registry.yaml.", file=sys.stderr)
        return 2

    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"help", "-h", "--help"}:
        print(usage(anatomy_key, entry))
        return 0

    action = args[0]
    action_config = entry.get("actions", {}).get(action)
    if action_config is None:
        print(f"Unsupported action `{action}` for `{anatomy_key}`.\n", file=sys.stderr)
        print(usage(anatomy_key, entry), file=sys.stderr)
        return 2

    target = root / action_config["target"]
    command = [sys.executable, str(target), *action_config.get("default_args", []), *args[1:]]
    completed = subprocess.run(command, cwd=root, check=False)
    return completed.returncode
