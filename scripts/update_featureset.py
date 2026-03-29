from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fnmatch
from pathlib import Path
import subprocess

try:
    from bootstrap_brain import apply_discovery, collect_discovery
    from brain_utils import dump_json_stdout, dump_yaml_file, load_yaml_file, repo_root_from
    from runtime_bridge import build_runtime_registry
except ModuleNotFoundError:
    from scripts.bootstrap_brain import apply_discovery, collect_discovery
    from scripts.brain_utils import dump_json_stdout, dump_yaml_file, load_yaml_file, repo_root_from
    from scripts.runtime_bridge import build_runtime_registry


def git(root: Path, *args: str, timeout_seconds: int | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            args=["git", *args],
            returncode=124,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") or f"git {' '.join(args)} timed out after {timeout_seconds}s",
        )


def output_text(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stdout.strip() or result.stderr.strip()).strip()


def load_autopilot(root: Path) -> dict:
    return load_yaml_file(root / "orchestrator/autopilot.yaml").get("autopilot", {})


def load_autopilot_state(root: Path) -> dict:
    return load_yaml_file(root / "telemetry/autopilot_state.yaml")


def write_autopilot_state(root: Path, updates: dict) -> None:
    path = root / "telemetry/autopilot_state.yaml"
    payload = load_autopilot_state(root)
    state = payload.setdefault("state", {})
    state.update(updates)
    payload["last_updated"] = datetime.now(timezone.utc).date().isoformat()
    dump_yaml_file(path, payload)


def write_discovery_refresh(root: Path, discovery: dict, reason: str) -> None:
    path = root / "telemetry/discovery_state.yaml"
    payload = load_yaml_file(path)
    state = payload.setdefault("state", {})
    timestamp = datetime.now(timezone.utc).isoformat()
    state["repo_root"] = str(root)
    state["watch_roots"] = discovery.get("watch_roots", [])
    state["discovery_counts"] = discovery["combined"]["counts"]
    state["last_startup_check_at"] = timestamp
    state["last_full_audit_at"] = timestamp
    state["last_change_detected"] = True
    state["last_change_summary"] = [reason]
    payload["last_updated"] = datetime.now(timezone.utc).date().isoformat()
    dump_yaml_file(path, payload)


def git_available(root: Path) -> tuple[bool, str]:
    result = git(root, "rev-parse", "--is-inside-work-tree")
    inside = result.returncode == 0 and output_text(result) == "true"
    return inside, output_text(result)


def git_metadata(root: Path) -> dict:
    branch_result = git(root, "branch", "--show-current")
    head_result = git(root, "rev-parse", "HEAD")
    upstream_result = git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    dirty_result = git(root, "status", "--porcelain", "--untracked-files=all")

    upstream = output_text(upstream_result) if upstream_result.returncode == 0 else None
    upstream_head = None
    ahead = 0
    behind = 0

    if upstream:
        upstream_head_result = git(root, "rev-parse", upstream)
        if upstream_head_result.returncode == 0:
            upstream_head = output_text(upstream_head_result)
        compare_result = git(root, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        if compare_result.returncode == 0:
            parts = output_text(compare_result).split()
            if len(parts) == 2:
                try:
                    ahead = int(parts[0])
                    behind = int(parts[1])
                except ValueError:
                    ahead = 0
                    behind = 0

    blocking_dirty_paths, ignored_dirty_paths = dirty_paths(root, dirty_result.stdout.splitlines(), load_autopilot(root).get("updates", {}).get("dirty_policy", {}))

    return {
        "branch": output_text(branch_result) if branch_result.returncode == 0 else None,
        "head_sha": output_text(head_result) if head_result.returncode == 0 else None,
        "upstream_ref": upstream,
        "upstream_head_sha": upstream_head,
        "ahead_count": ahead,
        "behind_count": behind,
        "dirty": bool(blocking_dirty_paths) if dirty_result.returncode == 0 else False,
        "blocking_dirty_paths": blocking_dirty_paths,
        "ignored_dirty_paths": ignored_dirty_paths,
    }


def parse_status_path(line: str) -> str | None:
    if len(line) < 4:
        return None
    path = line[3:].strip()
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    return path or None


def matches_any(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


def dirty_paths(root: Path, lines: list[str], dirty_policy: dict) -> tuple[list[str], list[str]]:
    always_ignore = list(dirty_policy.get("always_ignore", []))
    ignore_for_update_check = list(dirty_policy.get("ignore_for_update_check", []))
    blocking = []
    ignored = []
    for line in lines:
        path = parse_status_path(line)
        if not path:
            continue
        if matches_any(path, always_ignore) or matches_any(path, ignore_for_update_check):
            ignored.append(path)
            continue
        blocking.append(path)
    return sorted(set(blocking)), sorted(set(ignored))


def should_refresh(previous: dict, current: dict) -> tuple[bool, list[str]]:
    reasons = []
    for key in ("branch", "head_sha", "upstream_head_sha"):
        if previous.get(f"last_git_{key}") != current.get(key) and current.get(key) is not None:
            reasons.append(f"{key}_changed")
    if previous.get("last_git_dirty") != current.get("dirty"):
        reasons.append("dirty_state_changed")
    if current.get("behind_count", 0) > 0:
        reasons.append("upstream_behind")
    return bool(reasons), reasons


def maybe_fetch(root: Path, updates_config: dict) -> dict:
    if not updates_config.get("check_git_remote", True):
        return {"attempted": False, "ok": True, "detail": "disabled"}
    timeout_seconds = int(updates_config.get("git_fetch_timeout_seconds", 15))
    result = git(root, "fetch", "--quiet", timeout_seconds=timeout_seconds)
    return {
        "attempted": True,
        "ok": result.returncode == 0,
        "detail": output_text(result),
    }


def maybe_fast_forward(root: Path, updates_config: dict, snapshot: dict, dry_run: bool) -> dict:
    if not updates_config.get("auto_fast_forward_when_clean", True):
        return {"attempted": False, "status": "disabled"}
    if snapshot.get("behind_count", 0) <= 0:
        return {"attempted": False, "status": "not_behind"}
    if snapshot.get("ahead_count", 0) > 0:
        return {"attempted": False, "status": "ahead_of_upstream"}
    if updates_config.get("require_clean_worktree_for_pull", True) and snapshot.get("dirty", False):
        return {"attempted": False, "status": "dirty_worktree"}
    if dry_run:
        return {"attempted": True, "status": "dry_run"}

    result = git(root, "pull", "--ff-only")
    return {
        "attempted": True,
        "status": "updated" if result.returncode == 0 else "failed",
        "detail": output_text(result),
    }


def refresh_featureset(root: Path, reason: str, dry_run: bool) -> dict:
    if dry_run:
        return {
            "refreshed": True,
            "reason": reason,
            "counts": None,
            "dry_run": True,
        }
    discovery = collect_discovery(root)
    apply_discovery(root, discovery)
    build_runtime_registry(root, write=True)
    write_discovery_refresh(root, discovery, reason)
    return {
        "refreshed": True,
        "reason": reason,
        "counts": discovery["combined"]["counts"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check git state and refresh the featureset when the repository changes.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    inside_repo, detail = git_available(root)
    if not inside_repo:
        dump_json_stdout({"git_repo": False, "status": "skipped", "detail": detail or "not_a_git_repository"})
        return 0

    autopilot = load_autopilot(root)
    updates_config = autopilot.get("updates", {})
    if not updates_config.get("enabled", True):
        dump_json_stdout({"git_repo": True, "status": "disabled"})
        return 0
    previous_state = load_autopilot_state(root).get("state", {})

    fetch_result = maybe_fetch(root, updates_config)
    before = git_metadata(root)
    changed, reasons = should_refresh(previous_state, before)
    pull_result = maybe_fast_forward(root, updates_config, before, args.dry_run)
    after = git_metadata(root)

    refreshed = {"refreshed": False, "reason": None}
    refresh_on_change = updates_config.get("refresh_featureset_on_git_change", True)
    if pull_result.get("status") == "updated" or (refresh_on_change and changed):
        reason = "fast_forward_applied" if pull_result.get("status") == "updated" else "git_state_changed"
        refreshed = refresh_featureset(root, reason, args.dry_run)

    status = "unchanged"
    if pull_result.get("status") == "failed":
        status = "update_failed"
    elif refreshed.get("refreshed"):
        status = "featureset_refreshed"
    elif reasons:
        status = "change_detected"

    if not args.dry_run:
        timestamp = datetime.now(timezone.utc).isoformat()
        write_autopilot_state(
            root,
            {
                "last_git_check_at": timestamp,
                "last_git_branch": after.get("branch"),
                "last_git_head_sha": after.get("head_sha"),
                "last_git_upstream_ref": after.get("upstream_ref"),
                "last_git_upstream_head_sha": after.get("upstream_head_sha"),
                "last_git_ahead_count": after.get("ahead_count", 0),
                "last_git_behind_count": after.get("behind_count", 0),
                "last_git_dirty": after.get("dirty", False),
                "last_featureset_update_at": timestamp if refreshed.get("refreshed") else previous_state.get("last_featureset_update_at"),
                "last_featureset_update_status": status,
                "last_featureset_update_reason": refreshed.get("reason") or ",".join(reasons) or "no_change",
            },
        )

    dump_json_stdout(
        {
            "git_repo": True,
            "status": status,
            "fetch": fetch_result,
            "pull": pull_result,
            "changed": changed,
            "reasons": reasons,
            "before": before,
            "after": after,
            "blocking_dirty_paths": after.get("blocking_dirty_paths", []),
            "ignored_dirty_paths": after.get("ignored_dirty_paths", []),
            "featureset": refreshed,
        }
    )
    return 1 if pull_result.get("status") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
