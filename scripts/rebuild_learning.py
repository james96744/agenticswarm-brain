from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone

try:
    from brain_utils import dump_json_stdout, dump_yaml_file, load_yaml_file, repo_root_from
    from sovereign_memory import ensure_state_files, rebuild_portable_intelligence
except ModuleNotFoundError:
    from scripts.brain_utils import dump_json_stdout, dump_yaml_file, load_yaml_file, repo_root_from
    from scripts.sovereign_memory import ensure_state_files, rebuild_portable_intelligence


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_now() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _route_success(route: dict) -> bool:
    return route.get("status") == "success" and route.get("critic_status") == "passed"


def _verified_route(route: dict) -> bool:
    return bool(route.get("verified_execution")) or _route_success(route)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def rebuild_learning_state(root, *, top_per_family: int = 3) -> dict:
    ensure_state_files(root)
    routes_path = root / "telemetry" / "routes.yaml"
    benchmarks_path = root / "capabilities" / "benchmarks.yaml"
    routes_payload = load_yaml_file(routes_path)
    benchmarks_payload = load_yaml_file(benchmarks_path)

    task_rows = {}
    model_rows = {}
    agent_rows = {}
    adapter_rows = {}
    preference_rows = defaultdict(list)
    route_clusters = defaultdict(
        lambda: {
            "run_count": 0,
            "verified_execution_count": 0,
            "replay_candidate_count": 0,
            "success_count": 0,
            "avg_replay_score_total": 0.0,
            "avg_latency_total": 0.0,
            "avg_total_tokens_total": 0.0,
            "last_run_id": None,
            "updated_at": None,
        }
    )
    real_routes = [route for route in routes_payload.get("routes", []) if not route.get("simulated", False)]

    def task_row(task_family: str) -> dict:
        row = task_rows.get(task_family)
        if row is None:
            row = {
                "task_family": task_family,
                "run_count": 0,
                "success_count": 0,
                "critic_pass_count": 0,
                "verified_execution_count": 0,
                "replay_candidate_count": 0,
                "avg_confidence_total": 0.0,
                "avg_latency_total": 0.0,
                "avg_total_tokens_total": 0.0,
                "avg_prompt_tokens_total": 0.0,
                "avg_completion_tokens_total": 0.0,
                "avg_tool_context_tokens_total": 0.0,
                "queued_run_count": 0,
                "remote_dispatch_count": 0,
                "last_executor_id": None,
                "last_router_id": None,
                "updated_at": None,
            }
            task_rows[task_family] = row
        return row

    def model_row(model_id: str, task_family: str) -> dict:
        key = (model_id, task_family)
        row = model_rows.get(key)
        if row is None:
            row = {
                "model_id": model_id,
                "task_family": task_family,
                "run_count": 0,
                "success_count": 0,
                "critic_pass_count": 0,
                "avg_latency_total": 0.0,
                "avg_total_tokens_total": 0.0,
                "last_used_at": None,
            }
            model_rows[key] = row
        return row

    def agent_row(agent_id: str, task_family: str) -> dict:
        key = (agent_id, task_family)
        row = agent_rows.get(key)
        if row is None:
            row = {
                "agent_id": agent_id,
                "task_family": task_family,
                "run_count": 0,
                "success_count": 0,
                "critic_failure_count": 0,
                "avg_confidence_total": 0.0,
                "avg_latency_total": 0.0,
                "avg_total_tokens_total": 0.0,
                "prune_protected": False,
                "updated_at": None,
            }
            agent_rows[key] = row
        return row

    def adapter_row(backend_id: str, task_family: str, dispatch_mode: str) -> dict:
        key = (backend_id, task_family)
        row = adapter_rows.get(key)
        if row is None:
            row = {
                "adapter_id": f"backend:{backend_id}:{task_family}",
                "task_family": task_family,
                "run_count": 0,
                "success_count": 0,
                "avg_latency_total": 0.0,
                "avg_total_tokens_total": 0.0,
                "dispatch_mode": dispatch_mode,
                "last_status": None,
                "updated_at": None,
            }
            adapter_rows[key] = row
        return row

    for route in real_routes:
        task_family = route.get("task_family")
        if not task_family:
            continue
        success = route.get("status") == "success"
        verified = _verified_route(route)
        confidence = _safe_float(route.get("confidence"))
        latency_ms = _safe_int(route.get("latency_ms"))
        total_tokens = _safe_int(route.get("total_tokens"))
        prompt_tokens = _safe_int(route.get("prompt_tokens"))
        completion_tokens = _safe_int(route.get("completion_tokens"))
        tool_context_tokens = _safe_int(route.get("tool_context_tokens"))
        replay_score = _safe_float(route.get("replay_score", 1.0 if verified else 0.0))
        timestamp = route.get("timestamp", _utc_now())

        task = task_row(task_family)
        task["run_count"] += 1
        task["success_count"] += 1 if success else 0
        task["critic_pass_count"] += 1 if route.get("critic_status") == "passed" else 0
        task["verified_execution_count"] += 1 if verified else 0
        task["replay_candidate_count"] += 1 if route.get("replay_eligible") else 0
        task["avg_confidence_total"] += confidence
        task["avg_latency_total"] += latency_ms
        task["avg_total_tokens_total"] += total_tokens
        task["avg_prompt_tokens_total"] += prompt_tokens
        task["avg_completion_tokens_total"] += completion_tokens
        task["avg_tool_context_tokens_total"] += tool_context_tokens
        task["queued_run_count"] += 1 if route.get("dispatch_mode") == "deferred" else 0
        task["remote_dispatch_count"] += 1 if route.get("dispatch_mode") == "remote_worker" else 0
        if timestamp >= str(task.get("updated_at") or ""):
            task["last_executor_id"] = route.get("executor_id")
            task["last_router_id"] = route.get("router_id")
            task["updated_at"] = timestamp

        router_id = route.get("router_id")
        if router_id:
            model = model_row(router_id, task_family)
            model["run_count"] += 1
            model["success_count"] += 1 if success else 0
            model["critic_pass_count"] += 1 if route.get("critic_status") == "passed" else 0
            model["avg_latency_total"] += latency_ms
            model["avg_total_tokens_total"] += total_tokens
            if timestamp >= str(model.get("last_used_at") or ""):
                model["last_used_at"] = timestamp

        executor_id = route.get("executor_id")
        if executor_id:
            agent = agent_row(executor_id, task_family)
            agent["run_count"] += 1
            agent["success_count"] += 1 if success else 0
            agent["critic_failure_count"] += 1 if route.get("critic_status") == "failed" else 0
            agent["avg_confidence_total"] += confidence
            agent["avg_latency_total"] += latency_ms
            agent["avg_total_tokens_total"] += total_tokens
            if timestamp >= str(agent.get("updated_at") or ""):
                agent["updated_at"] = timestamp

        for backend_id in route.get("backend_ids", []):
            adapter = adapter_row(backend_id, task_family, route.get("dispatch_mode", "immediate"))
            adapter["run_count"] += 1
            adapter["success_count"] += 1 if success else 0
            adapter["avg_latency_total"] += latency_ms
            adapter["avg_total_tokens_total"] += total_tokens
            adapter["dispatch_mode"] = route.get("dispatch_mode", "immediate")
            adapter["last_status"] = route.get("status")
            if timestamp >= str(adapter.get("updated_at") or ""):
                adapter["updated_at"] = timestamp

        if verified:
            cluster_key = (
                task_family,
                route.get("executor_id"),
                route.get("router_id"),
                tuple(sorted(route.get("backend_ids", []))),
                route.get("dispatch_mode", "immediate"),
            )
            cluster = route_clusters[cluster_key]
            cluster["run_count"] += 1
            cluster["verified_execution_count"] += 1
            cluster["replay_candidate_count"] += 1 if route.get("replay_eligible") else 0
            cluster["success_count"] += 1 if success else 0
            cluster["avg_replay_score_total"] += replay_score
            cluster["avg_latency_total"] += latency_ms
            cluster["avg_total_tokens_total"] += total_tokens
            if timestamp >= str(cluster.get("updated_at") or ""):
                cluster["last_run_id"] = route.get("run_id")
                cluster["updated_at"] = timestamp

    rebuilt_task_rows = []
    for task_family, row in sorted(task_rows.items()):
        run_count = max(1, row["run_count"])
        rebuilt_task_rows.append(
            {
                "task_family": task_family,
                "run_count": row["run_count"],
                "success_count": row["success_count"],
                "critic_pass_count": row["critic_pass_count"],
                "verified_execution_count": row["verified_execution_count"],
                "replay_candidate_count": row["replay_candidate_count"],
                "avg_confidence": round(row["avg_confidence_total"] / run_count, 4),
                "avg_latency_ms": round(row["avg_latency_total"] / run_count, 2),
                "avg_total_tokens": round(row["avg_total_tokens_total"] / run_count, 2),
                "avg_prompt_tokens": round(row["avg_prompt_tokens_total"] / run_count, 2),
                "avg_completion_tokens": round(row["avg_completion_tokens_total"] / run_count, 2),
                "avg_tool_context_tokens": round(row["avg_tool_context_tokens_total"] / run_count, 2),
                "queued_run_count": row["queued_run_count"],
                "remote_dispatch_count": row["remote_dispatch_count"],
                "last_executor_id": row["last_executor_id"],
                "last_router_id": row["last_router_id"],
                "updated_at": row["updated_at"] or _utc_now(),
            }
        )

    rebuilt_model_rows = []
    for _, row in sorted(model_rows.items()):
        run_count = max(1, row["run_count"])
        rebuilt_model_rows.append(
            {
                "model_id": row["model_id"],
                "task_family": row["task_family"],
                "run_count": row["run_count"],
                "success_count": row["success_count"],
                "critic_pass_count": row["critic_pass_count"],
                "avg_latency_ms": round(row["avg_latency_total"] / run_count, 2),
                "avg_total_tokens": round(row["avg_total_tokens_total"] / run_count, 2),
                "last_used_at": row["last_used_at"] or _utc_now(),
            }
        )

    rebuilt_agent_rows = []
    for _, row in sorted(agent_rows.items()):
        run_count = max(1, row["run_count"])
        critic_failure_count = row["critic_failure_count"]
        rebuilt_agent_rows.append(
            {
                "agent_id": row["agent_id"],
                "task_family": row["task_family"],
                "run_count": row["run_count"],
                "success_count": row["success_count"],
                "critic_failure_count": critic_failure_count,
                "avg_confidence": round(row["avg_confidence_total"] / run_count, 4),
                "avg_latency_ms": round(row["avg_latency_total"] / run_count, 2),
                "avg_total_tokens": round(row["avg_total_tokens_total"] / run_count, 2),
                "prune_protected": row["prune_protected"],
                "value_add_per_token": round((row["avg_confidence_total"] * 1000.0) / max(1.0, row["avg_total_tokens_total"]), 4),
                "critic_rejection_rate": round(critic_failure_count / run_count, 4),
                "ignored_edit_rate": 0.0,
                "updated_at": row["updated_at"] or _utc_now(),
            }
        )

    rebuilt_adapter_rows = []
    for _, row in sorted(adapter_rows.items()):
        run_count = max(1, row["run_count"])
        rebuilt_adapter_rows.append(
            {
                "adapter_id": row["adapter_id"],
                "task_family": row["task_family"],
                "run_count": row["run_count"],
                "success_count": row["success_count"],
                "avg_latency_ms": round(row["avg_latency_total"] / run_count, 2),
                "avg_total_tokens": round(row["avg_total_tokens_total"] / run_count, 2),
                "dispatch_mode": row["dispatch_mode"],
                "last_status": row["last_status"],
                "updated_at": row["updated_at"] or _utc_now(),
            }
        )

    for (task_family, executor_id, router_id, backend_ids, dispatch_mode), row in route_clusters.items():
        run_count = max(1, row["run_count"])
        preference_rows[task_family].append(
            {
                "task_family": task_family,
                "executor_id": executor_id,
                "router_id": router_id,
                "backend_ids": list(backend_ids),
                "dispatch_mode": dispatch_mode,
                "run_count": row["run_count"],
                "verified_execution_count": row["verified_execution_count"],
                "replay_candidate_count": row["replay_candidate_count"],
                "success_rate": round(row["success_count"] / run_count, 4),
                "avg_replay_score": round(row["avg_replay_score_total"] / run_count, 4),
                "avg_latency_ms": round(row["avg_latency_total"] / run_count, 2),
                "avg_total_tokens": round(row["avg_total_tokens_total"] / run_count, 2),
                "last_run_id": row["last_run_id"],
                "updated_at": row["updated_at"] or _utc_now(),
            }
        )

    rebuilt_preferences = []
    for _, rows in sorted(preference_rows.items()):
        ranked = sorted(
            rows,
            key=lambda item: (
                float(item.get("avg_replay_score", 0.0)),
                float(item.get("success_rate", 0.0)),
                int(item.get("verified_execution_count", 0)),
                -float(item.get("avg_total_tokens", 0.0)),
                -float(item.get("avg_latency_ms", 0.0)),
            ),
            reverse=True,
        )
        for rank, row in enumerate(ranked[:top_per_family], start=1):
            rebuilt_preferences.append({**row, "rank": rank})

    rebuilt_benchmarks = {
        **benchmarks_payload,
        "last_updated": _date_now(),
        "task_family_benchmarks": rebuilt_task_rows,
        "model_benchmarks": rebuilt_model_rows,
        "agent_value_metrics": rebuilt_agent_rows,
        "adapter_benchmarks": rebuilt_adapter_rows,
    }
    rebuilt_benchmarks.setdefault("agent_pair_metrics", benchmarks_payload.get("agent_pair_metrics", []))
    rebuilt_routes = {
        **routes_payload,
        "last_updated": _date_now(),
        "route_preferences": rebuilt_preferences,
    }
    return {
        "benchmarks": rebuilt_benchmarks,
        "routes": rebuilt_routes,
        "summary": {
            "real_routes": len(real_routes),
            "verified_routes": len([route for route in real_routes if _verified_route(route)]),
            "task_family_benchmarks": len(rebuilt_task_rows),
            "model_benchmarks": len(rebuilt_model_rows),
            "agent_value_metrics": len(rebuilt_agent_rows),
            "adapter_benchmarks": len(rebuilt_adapter_rows),
            "route_preferences": len(rebuilt_preferences),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild benchmark rollups and replay preferences from accumulated route telemetry.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--top-per-family", type=int, default=3)
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    rebuilt = rebuild_learning_state(root, top_per_family=max(1, args.top_per_family))
    portable_result = rebuild_portable_intelligence(root, write=not args.dry_run)
    if not args.dry_run:
        dump_yaml_file(root / "capabilities/benchmarks.yaml", rebuilt["benchmarks"])
        dump_yaml_file(root / "telemetry/routes.yaml", rebuilt["routes"])
    dump_json_stdout({"dry_run": args.dry_run, **rebuilt["summary"], **portable_result["summary"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
