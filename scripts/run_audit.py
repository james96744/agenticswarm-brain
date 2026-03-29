from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import plistlib
import py_compile
import subprocess
import sys

try:
    import fcntl
except ModuleNotFoundError:  # pragma: no cover - non-POSIX fallback
    fcntl = None

try:
    from bootstrap_brain import apply_discovery, collect_discovery
    from brain_utils import dump_json_stdout, dump_yaml_file, load_yaml_file, repo_root_from
    from validate_brain import run_validation
except ModuleNotFoundError:
    from scripts.bootstrap_brain import apply_discovery, collect_discovery
    from scripts.brain_utils import dump_json_stdout, dump_yaml_file, load_yaml_file, repo_root_from
    from scripts.validate_brain import run_validation


RUNTIME_CHECKS = (
    "scripts/simulate_swarm.py",
    "scripts/reconcile_memory.py",
    "scripts/prune_topology.py",
    "scripts/prepare_distillation.py",
)

MAINTENANCE_SCRIPTS = (
    ("scripts/reconcile_memory.py", "reconcile_memory"),
    ("scripts/prune_topology.py", "prune_topology"),
    ("scripts/prepare_distillation.py", "prepare_distillation"),
)


@contextmanager
def audit_lock(root: Path):
    lock_path = root / "telemetry" / "audit.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("w", encoding="utf-8")
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    try:
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def load_autopilot_config(root: Path) -> dict:
    payload = load_yaml_file(root / "orchestrator/autopilot.yaml")
    return payload.get("autopilot", {})


def load_discovery_state(root: Path) -> dict:
    payload = load_yaml_file(root / "telemetry/discovery_state.yaml")
    return payload.get("state", {})


def load_autopilot_state(root: Path) -> dict:
    payload = load_yaml_file(root / "telemetry/autopilot_state.yaml")
    return payload.get("state", {})


def write_autopilot_state(root: Path, updates: dict) -> None:
    path = root / "telemetry/autopilot_state.yaml"
    payload = load_yaml_file(path)
    state = payload.setdefault("state", {})
    state.update(updates)
    payload["last_updated"] = datetime.now(timezone.utc).date().isoformat()
    dump_yaml_file(path, payload)


def compile_scripts(root: Path) -> tuple[bool, list[dict]]:
    results = []
    scripts_dir = root / "scripts"
    success = True
    for path in sorted(scripts_dir.glob("*.py")):
        try:
            py_compile.compile(str(path), doraise=True)
            results.append({"phase": "compile", "target": str(path.relative_to(root)), "status": "passed"})
        except py_compile.PyCompileError as exc:
            success = False
            results.append(
                {
                    "phase": "compile",
                    "target": str(path.relative_to(root)),
                    "status": "failed",
                    "detail": str(exc),
                }
            )
    return success, results


def run_runtime_checks(root: Path) -> tuple[bool, list[dict]]:
    results = []
    success = True
    for script in RUNTIME_CHECKS:
        completed = subprocess.run(
            [sys.executable, str(root / script), "--repo-root", str(root), "--dry-run"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        status = "passed" if completed.returncode == 0 else "failed"
        if completed.returncode != 0:
            success = False
        detail = completed.stdout.strip() or completed.stderr.strip()
        results.append(
            {
                "phase": "runtime_check",
                "target": script,
                "status": status,
                "detail": detail,
            }
        )
    return success, results


def run_script(root: Path, script: str, *, dry_run: bool) -> tuple[bool, dict]:
    command = [sys.executable, str(root / script), "--repo-root", str(root)]
    if dry_run:
        command.append("--dry-run")
    completed = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    status = "passed" if completed.returncode == 0 else "failed"
    detail = completed.stdout.strip() or completed.stderr.strip()
    return completed.returncode == 0, {"phase": "maintenance", "target": script, "status": status, "detail": detail}


def telemetry_routes_empty(root: Path) -> bool:
    payload = load_yaml_file(root / "telemetry/routes.yaml")
    return not payload.get("routes", [])


def run_maintenance(root: Path, autopilot: dict, *, dry_run: bool) -> tuple[bool, list[dict]]:
    results = []
    success = True
    maintenance = autopilot.get("maintenance", {})

    if maintenance.get("seed_simulation_if_routes_empty", False) and telemetry_routes_empty(root):
        ok, result = run_script(root, "scripts/simulate_swarm.py", dry_run=dry_run)
        success = success and ok
        results.append(result)

    for script, config_key in MAINTENANCE_SCRIPTS:
        if not maintenance.get(config_key, False):
            results.append({"phase": "maintenance", "target": script, "status": "skipped"})
            continue
        ok, result = run_script(root, script, dry_run=dry_run)
        success = success and ok
        results.append(result)

    if not dry_run:
        write_autopilot_state(
            root,
            {
                "enabled": autopilot.get("enabled", True),
                "last_maintenance_run_at": datetime.now(timezone.utc).isoformat(),
                "last_maintenance_summary": [f"{item['target']}:{item['status']}" for item in results],
            },
        )

    return success, results


def compute_fingerprints(paths: list[str]) -> dict[str, int | None]:
    fingerprints: dict[str, int | None] = {}
    for path_str in sorted(set(paths)):
        path = Path(path_str)
        if not path.exists():
            fingerprints[path_str] = None
            continue
        try:
            fingerprints[path_str] = path.stat().st_mtime_ns
        except OSError:
            fingerprints[path_str] = None
    return fingerprints


def write_discovery_state(
    root: Path,
    *,
    watch_roots: list[str],
    discovery_counts: dict,
    timestamp: str,
    changed: bool,
    change_summary: list[str],
    full_audit: bool,
) -> None:
    path = root / "telemetry/discovery_state.yaml"
    payload = load_yaml_file(path)
    state = payload.setdefault("state", {})
    state["repo_root"] = str(root)
    state["watch_roots"] = watch_roots
    state["fingerprints"] = compute_fingerprints(watch_roots)
    state["discovery_counts"] = discovery_counts
    state["last_startup_check_at"] = timestamp
    state["last_change_detected"] = changed
    state["last_change_summary"] = change_summary
    if full_audit:
        state["last_full_audit_at"] = timestamp
    payload["last_updated"] = datetime.now(timezone.utc).date().isoformat()
    dump_yaml_file(path, payload)


def compare_discovery_state(root: Path) -> tuple[bool, list[str], list[str]]:
    state = load_discovery_state(root)
    watch_roots = state.get("watch_roots", [])
    if not watch_roots:
        return True, ["no_watch_roots_recorded"], []

    previous = state.get("fingerprints", {})
    current = compute_fingerprints(watch_roots)
    summary = []
    changed = False

    for path_str in sorted(set(previous) | set(current)):
        previous_value = previous.get(path_str)
        current_value = current.get(path_str)
        if previous_value != current_value:
            changed = True
            if previous_value is None and current_value is not None:
                summary.append(f"created:{path_str}")
            elif previous_value is not None and current_value is None:
                summary.append(f"removed:{path_str}")
            else:
                summary.append(f"modified:{path_str}")

    return changed, summary, watch_roots


def append_audit_report(root: Path, report: dict) -> None:
    path = root / "telemetry/audit_report.yaml"
    payload = load_yaml_file(path)
    reports = payload.setdefault("reports", [])
    reports.append(report)
    payload["last_updated"] = datetime.now(timezone.utc).date().isoformat()
    dump_yaml_file(path, payload)


def launch_agent_paths(root: Path) -> tuple[str, Path]:
    slug = hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:12]
    label = f"com.lahaolesolutions.agenticswarm.{slug}"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    return label, plist_path


def install_launchd_autostart(root: Path, autopilot: dict, *, dry_run: bool) -> tuple[bool, dict]:
    interval = int(autopilot.get("startup_recheck_interval_seconds", 900))
    label, plist_path = launch_agent_paths(root)
    stdout_path = root / "telemetry" / "autopilot.stdout.log"
    stderr_path = root / "telemetry" / "autopilot.stderr.log"
    plist = {
        "Label": label,
        "ProgramArguments": [
            sys.executable,
            str(root / "scripts/run_audit.py"),
            "--repo-root",
            str(root),
            "--startup-check",
            "--skip-runtime-checks",
        ],
        "WorkingDirectory": str(root),
        "RunAtLoad": bool(autopilot.get("autostart", {}).get("darwin", {}).get("run_at_load", True)),
        "KeepAlive": bool(autopilot.get("autostart", {}).get("darwin", {}).get("keep_alive", False)),
        "StartInterval": interval,
        "StandardOutPath": str(stdout_path),
        "StandardErrorPath": str(stderr_path),
    }

    if dry_run:
        return True, {
            "phase": "autostart",
            "status": "skipped",
            "detail": f"dry_run launchd install for {label}",
        }

    plist_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with plist_path.open("wb") as handle:
        plistlib.dump(plist, handle)

    commands = [
        ["launchctl", "bootout", f"gui/{os.getuid()}", str(plist_path)],
        ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist_path)],
        ["launchctl", "enable", f"gui/{os.getuid()}/{label}"],
        ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{label}"],
    ]
    command_results = []
    success = True
    for index, command in enumerate(commands):
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        detail = completed.stdout.strip() or completed.stderr.strip()
        command_results.append(f"{' '.join(command)} => {completed.returncode}:{detail}")
        if completed.returncode != 0 and index > 0:
            success = False

    write_autopilot_state(
        root,
        {
            "enabled": True,
            "autostart_installed": success,
            "autostart_platform": sys.platform,
            "autostart_label": label,
            "autostart_path": str(plist_path),
            "last_install_attempt_at": datetime.now(timezone.utc).isoformat(),
            "last_install_status": "installed" if success else "failed",
            "last_install_error": None if success else " | ".join(command_results),
        },
    )

    return success, {
        "phase": "autostart",
        "status": "passed" if success else "failed",
        "target": str(plist_path),
        "detail": " | ".join(command_results),
    }


def ensure_autostart(root: Path, autopilot: dict, *, dry_run: bool, no_autostart: bool, startup_mode: bool) -> tuple[bool, dict]:
    if no_autostart:
        return True, {"phase": "autostart", "status": "skipped", "detail": "disabled_by_flag"}
    if os.environ.get("CI"):
        return True, {"phase": "autostart", "status": "skipped", "detail": "ci_environment"}
    if startup_mode:
        return True, {"phase": "autostart", "status": "skipped", "detail": "startup_mode"}
    if not autopilot.get("enabled", True):
        return True, {"phase": "autostart", "status": "skipped", "detail": "autopilot_disabled"}
    if not autopilot.get("install_autostart_on_manual_audit", True):
        return True, {"phase": "autostart", "status": "skipped", "detail": "config_disabled"}
    if sys.platform != "darwin":
        return True, {"phase": "autostart", "status": "skipped", "detail": f"unsupported_platform:{sys.platform}"}
    if not shutil_which("launchctl"):
        return False, {"phase": "autostart", "status": "failed", "detail": "launchctl_not_found"}
    return install_launchd_autostart(root, autopilot, dry_run=dry_run)


def shutil_which(command: str) -> str | None:
    return __import__("shutil").which(command)


def runtime_checks_enabled(autopilot: dict, *, startup_mode: bool, explicit_skip: bool) -> bool:
    if explicit_skip:
        return False
    if startup_mode:
        return autopilot.get("runtime_checks_on_startup_recheck", False)
    return autopilot.get("runtime_checks_on_manual_audit", True)


def perform_full_audit(
    root: Path,
    *,
    dry_run: bool,
    explicit_skip_runtime_checks: bool,
    no_autostart: bool,
    reason: str,
    extra_report_fields: dict | None = None,
    change_summary: list[str] | None = None,
    startup_mode: bool = False,
) -> tuple[dict, bool]:
    timestamp = datetime.now(timezone.utc).isoformat()
    autopilot = load_autopilot_config(root)
    phases: list[dict] = []

    discovery = collect_discovery(root)
    phases.append(
        {
            "phase": "discovery",
            "status": "passed",
            "reason": reason,
            "counts": discovery["combined"]["counts"],
        }
    )

    if not dry_run:
        apply_discovery(root, discovery)
        phases.append({"phase": "populate", "status": "passed"})
    else:
        phases.append({"phase": "populate", "status": "skipped", "detail": "dry_run"})

    compile_ok, compile_results = compile_scripts(root)
    phases.extend(compile_results)

    validation_errors = run_validation(root)
    phases.append(
        {
            "phase": "validation",
            "status": "passed" if not validation_errors else "failed",
            "error_count": len(validation_errors),
        }
    )

    runtime_ok = True
    if runtime_checks_enabled(autopilot, startup_mode=startup_mode, explicit_skip=explicit_skip_runtime_checks):
        runtime_ok, runtime_results = run_runtime_checks(root)
        phases.extend(runtime_results)
    else:
        phases.append({"phase": "runtime_check", "status": "skipped"})

    maintenance_ok, maintenance_results = run_maintenance(root, autopilot, dry_run=dry_run)
    phases.extend(maintenance_results)

    autostart_ok, autostart_result = ensure_autostart(
        root,
        autopilot,
        dry_run=dry_run,
        no_autostart=no_autostart,
        startup_mode=startup_mode,
    )
    phases.append(autostart_result)

    report = {
        "audit_id": f"audit-{timestamp}",
        "timestamp": timestamp,
        "repo_root": str(root),
        "dry_run": dry_run,
        "startup_mode": startup_mode,
        "phases": phases,
        "validation": {
            "passed": not validation_errors,
            "errors": validation_errors,
        },
        "discovery_counts": discovery["combined"]["counts"],
        "watch_roots": discovery.get("watch_roots", []),
    }
    if extra_report_fields:
        report.update(extra_report_fields)

    if not dry_run:
        write_discovery_state(
            root,
            watch_roots=discovery.get("watch_roots", []),
            discovery_counts=discovery["combined"]["counts"],
            timestamp=timestamp,
            changed=True,
            change_summary=change_summary or [reason],
            full_audit=True,
        )
        append_audit_report(root, report)

    success = compile_ok and not validation_errors and runtime_ok and maintenance_ok and autostart_ok
    return report, success


def perform_startup_check(root: Path, *, dry_run: bool, explicit_skip_runtime_checks: bool, no_autostart: bool) -> tuple[dict, bool]:
    timestamp = datetime.now(timezone.utc).isoformat()
    autopilot = load_autopilot_config(root)
    changed, change_summary, watch_roots = compare_discovery_state(root)

    if changed:
        return perform_full_audit(
            root,
            dry_run=dry_run,
            explicit_skip_runtime_checks=explicit_skip_runtime_checks,
            no_autostart=no_autostart,
            reason="startup_recheck_detected_changes",
            extra_report_fields={
                "startup_recheck": {
                    "changed": True,
                    "change_summary": change_summary,
                },
            },
            change_summary=change_summary,
            startup_mode=True,
        )

    validation_errors = run_validation(root)
    phases = [
        {
            "phase": "startup_recheck",
            "status": "passed",
            "changed": False,
            "watched_root_count": len(watch_roots),
        },
        {
            "phase": "validation",
            "status": "passed" if not validation_errors else "failed",
            "error_count": len(validation_errors),
        },
    ]

    maintenance_ok, maintenance_results = run_maintenance(root, autopilot, dry_run=dry_run)
    phases.extend(maintenance_results)

    phases.append({"phase": "autostart", "status": "skipped", "detail": "startup_mode"})

    report = {
        "audit_id": f"startup-{timestamp}",
        "timestamp": timestamp,
        "repo_root": str(root),
        "dry_run": dry_run,
        "startup_mode": True,
        "phases": phases,
        "validation": {
            "passed": not validation_errors,
            "errors": validation_errors,
        },
        "discovery_counts": load_discovery_state(root).get("discovery_counts", {}),
        "watch_roots": watch_roots,
        "startup_recheck": {
            "changed": False,
            "change_summary": [],
        },
    }

    if not dry_run:
        write_discovery_state(
            root,
            watch_roots=watch_roots,
            discovery_counts=report["discovery_counts"],
            timestamp=timestamp,
            changed=False,
            change_summary=[],
            full_audit=False,
        )
        append_audit_report(root, report)

    success = not validation_errors and maintenance_ok
    return report, success


def main() -> int:
    parser = argparse.ArgumentParser(description="Single-entry audit runner that discovers, populates, self-maintains, and installs automatic startup rechecks.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-runtime-checks", action="store_true")
    parser.add_argument("--startup-check", action="store_true")
    parser.add_argument("--no-autostart", action="store_true")
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)

    with audit_lock(root):
        if args.startup_check:
            report, success = perform_startup_check(
                root,
                dry_run=args.dry_run,
                explicit_skip_runtime_checks=args.skip_runtime_checks,
                no_autostart=args.no_autostart,
            )
        else:
            report, success = perform_full_audit(
                root,
                dry_run=args.dry_run,
                explicit_skip_runtime_checks=args.skip_runtime_checks,
                no_autostart=args.no_autostart,
                reason="manual_audit",
                startup_mode=False,
            )

    dump_json_stdout(report)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
