from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
from pathlib import Path
import shlex
import subprocess
import time
from urllib import error as urllib_error
from urllib import request as urllib_request
import uuid

try:
    from brain_utils import dump_yaml_file, load_yaml_file, repo_root_from
    from control_plane import BlackboardStore, ControlPlaneStore, utc_now
    from runtime_bridge import build_runtime_registry, plan_execution
    from sovereign_memory import ensure_state_files, record_execution_acceptance
except ModuleNotFoundError:
    from scripts.brain_utils import dump_yaml_file, load_yaml_file, repo_root_from
    from scripts.control_plane import BlackboardStore, ControlPlaneStore, utc_now
    from scripts.runtime_bridge import build_runtime_registry, plan_execution
    from scripts.sovereign_memory import ensure_state_files, record_execution_acceptance


@dataclass
class ExecutionRequest:
    task_id: str
    task_family: str
    description: str
    quality_target: str = "balanced"
    risk_level: str = "medium"
    complexity: str = "medium"
    requires_code: bool = False
    requires_tools: bool = False
    high_stakes: bool = False
    force_expert: bool = False
    timeout_seconds: int = 30
    workdir: str | None = None
    owner_id: str = "brain"
    approve_risky: bool = False
    dispatch_mode: str = "immediate"
    queue_name: str | None = None
    not_before_at: str | None = None
    max_retries: int = 1
    selected_executor_id: str | None = None
    selected_router_id: str | None = None
    selected_backend_ids: list[str] = field(default_factory=list)
    inputs: dict = field(default_factory=dict)
    bad_output: str | None = None
    expert_correction: str | None = None
    verified_correction: bool = False


@dataclass
class ExecutionRun:
    run_id: str
    task_id: str
    status: str
    selected_executor_id: str | None
    selected_router_id: str | None
    selected_backend_ids: list[str]
    dispatch_mode: str = "immediate"
    queue_name: str | None = None
    retry_count: int = 0
    approval_status: str = "not_required"
    current_step: str = "created"
    started_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    completed_at: str | None = None
    failure_reason: str | None = None
    confidence: float = 0.0


@dataclass
class ExecutionResult:
    status: str
    summary: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    backend_calls: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    failure_reason: str | None = None
    route: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    critic_status: str = "pending"
    latency_ms: int = 0
    token_usage: dict = field(default_factory=dict)


class RouterAdapter:
    def resolve(self, router: dict, route: dict) -> dict:
        if not router:
            return {"status": "missing", "model_assignments": route.get("model_assignments", {})}
        return {
            "status": "resolved",
            "router_id": router.get("router_id"),
            "provider": router.get("provider"),
            "kind": router.get("kind"),
            "model_assignments": route.get("model_assignments", {}),
        }


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _estimate_text_tokens(value) -> int:
    if value is None:
        return 0
    if isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, sort_keys=True, default=str)
    else:
        text = str(value)
    text = text.strip()
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _collect_token_usage(request: ExecutionRequest, executor_result: dict, backend_calls: list[dict], summary: str) -> dict:
    explicit = request.inputs.get("token_usage", {}) or request.inputs.get("provider_usage", {}) or {}
    prompt_tokens = _safe_int(explicit.get("prompt_tokens"))
    completion_tokens = _safe_int(explicit.get("completion_tokens"))
    tool_context_tokens = _safe_int(explicit.get("tool_context_tokens"))
    cache_read_tokens = _safe_int(explicit.get("cache_read_tokens"))
    cache_write_tokens = _safe_int(explicit.get("cache_write_tokens"))
    estimation_method = "provider_reported" if explicit else "estimated"

    if not explicit:
        prompt_tokens = _estimate_text_tokens(request.description)
        prompt_tokens += _estimate_text_tokens(request.quality_target)
        prompt_tokens += _estimate_text_tokens(request.risk_level)
        prompt_tokens += _estimate_text_tokens(request.inputs)
        prompt_tokens += _estimate_text_tokens(request.selected_backend_ids)
        completion_tokens = _estimate_text_tokens(summary)
        completion_tokens += _estimate_text_tokens(executor_result.get("stdout", ""))
        completion_tokens += _estimate_text_tokens(executor_result.get("stderr", ""))
        tool_context_tokens = _estimate_text_tokens(
            [
                {
                    "backend_id": call.get("backend_id"),
                    "status": call.get("status"),
                    "summary": call.get("summary"),
                    "stdout": call.get("stdout", "")[:800],
                    "stderr": call.get("stderr", "")[:400],
                }
                for call in backend_calls
            ]
        )

    total_tokens = prompt_tokens + completion_tokens + tool_context_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "tool_context_tokens": tool_context_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "total_tokens": total_tokens,
        "estimation_method": estimation_method,
    }


def _http_invoke(url: str, method: str, timeout_seconds: int, headers: dict | None = None, body: str | bytes | None = None) -> dict:
    request = urllib_request.Request(url=url, method=method.upper())
    for key, value in (headers or {}).items():
        request.add_header(str(key), str(value))
    data = None
    if body is not None:
        data = body.encode("utf-8") if isinstance(body, str) else body
    try:
        with urllib_request.urlopen(request, data=data, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            return {
                "status": "success",
                "stdout": response_body.strip(),
                "stderr": "",
                "exit_code": response.getcode(),
                "headers": dict(response.headers.items()),
            }
    except urllib_error.HTTPError as exc:
        return {
            "status": "failed",
            "stdout": (exc.read().decode("utf-8", errors="replace") if exc.fp else "").strip(),
            "stderr": str(exc),
            "exit_code": exc.code,
            "headers": dict(exc.headers.items()) if exc.headers else {},
        }
    except urllib_error.URLError as exc:
        return {
            "status": "failed",
            "stdout": "",
            "stderr": str(exc),
            "exit_code": None,
            "headers": {},
        }


def _material_change(previous: str | None, current: str | None) -> bool:
    if not previous or not current:
        return False
    if previous.strip() == current.strip():
        return False
    similarity = SequenceMatcher(a=previous.strip(), b=current.strip()).ratio()
    return similarity < 0.98


class ExecutorAdapter:
    def invoke(self, root: Path, executor: dict, request: ExecutionRequest) -> dict:
        executor_args = request.inputs.get("executor_args", [])
        command_override = request.inputs.get("command")
        timeout_seconds = max(1, int(request.timeout_seconds))

        if command_override:
            if isinstance(command_override, str):
                final_command = shlex.split(command_override)
            else:
                final_command = [str(part) for part in command_override]
        elif executor and executor.get("command"):
            final_command = [str(executor["command"]), *[str(arg) for arg in executor_args]]
        else:
            return {
                "status": "skipped",
                "summary": "Executor could not be invoked because no command was provided.",
                "stdout": "",
                "stderr": "",
                "exit_code": None,
                "failure_reason": "missing_executor_command",
            }

        completed = subprocess.run(
            final_command,
            cwd=request.workdir or root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "status": "success" if completed.returncode == 0 else "failed",
            "summary": f"Executor `{executor.get('executor_id') if executor else 'unknown'}` returned {completed.returncode}.",
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "exit_code": completed.returncode,
            "failure_reason": None if completed.returncode == 0 else f"executor_exit_{completed.returncode}",
            "command": final_command,
        }


class BackendAdapter:
    def invoke(self, root: Path, backend: dict, call: dict) -> dict:
        action = call.get("action", "describe")
        timeout_seconds = max(1, int(call.get("timeout_seconds", 30)))

        if backend.get("kind") == "cli":
            if action == "describe":
                return {
                    "backend_id": backend.get("backend_id"),
                    "status": "success",
                    "summary": f"CLI backend `{backend.get('backend_id')}` resolved.",
                    "stdout": "",
                    "stderr": "",
                    "exit_code": 0,
                }
            args = [str(arg) for arg in call.get("args", [])]
            final_command = [str(backend.get("command")), *args]
            completed = subprocess.run(
                final_command,
                cwd=call.get("cwd") or root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            return {
                "backend_id": backend.get("backend_id"),
                "status": "success" if completed.returncode == 0 else "failed",
                "summary": f"CLI backend `{backend.get('backend_id')}` returned {completed.returncode}.",
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
                "exit_code": completed.returncode,
                "command": final_command,
            }

        if backend.get("kind") == "mcp_server":
            if backend.get("command") and action == "raw_command":
                final_command = [str(backend["command"]), *[str(arg) for arg in call.get("args", [])]]
                completed = subprocess.run(
                    final_command,
                    cwd=call.get("cwd") or root,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
                return {
                    "backend_id": backend.get("backend_id"),
                    "status": "success" if completed.returncode == 0 else "failed",
                    "summary": f"MCP backend `{backend.get('backend_id')}` returned {completed.returncode}.",
                    "stdout": completed.stdout.strip(),
                    "stderr": completed.stderr.strip(),
                    "exit_code": completed.returncode,
                    "command": final_command,
                }
            if backend.get("url") and action in {"http_get", "http_post", "http_request"}:
                method = call.get("method") or ("POST" if action == "http_post" else "GET")
                body = call.get("body")
                if "json_body" in call:
                    body = json.dumps(call.get("json_body"))
                response = _http_invoke(
                    call.get("url") or backend.get("url"),
                    method,
                    timeout_seconds,
                    headers=dict(call.get("headers", {})),
                    body=body,
                )
                return {
                    "backend_id": backend.get("backend_id"),
                    "summary": f"MCP HTTP backend `{backend.get('backend_id')}` returned {response.get('exit_code')}.",
                    "url": call.get("url") or backend.get("url"),
                    "method": method,
                    **response,
                }
            return {
                "backend_id": backend.get("backend_id"),
                "status": "success",
                "summary": f"MCP backend `{backend.get('backend_id')}` resolved.",
                "stdout": "",
                "stderr": "",
                "exit_code": 0,
                "endpoint": backend.get("url") or backend.get("command"),
            }

        if backend.get("kind") == "http_api":
            if action not in {"http_get", "http_post", "http_request", "describe"}:
                action = "http_request"
            if action == "describe":
                return {
                    "backend_id": backend.get("backend_id"),
                    "status": "success",
                    "summary": f"HTTP backend `{backend.get('backend_id')}` resolved.",
                    "stdout": "",
                    "stderr": "",
                    "exit_code": 0,
                    "endpoint": backend.get("url"),
                }
            method = call.get("method") or ("POST" if action == "http_post" else "GET")
            body = call.get("body")
            if "json_body" in call:
                body = json.dumps(call.get("json_body"))
            response = _http_invoke(
                call.get("url") or backend.get("url"),
                method,
                timeout_seconds,
                headers=dict(call.get("headers", {})),
                body=body,
            )
            return {
                "backend_id": backend.get("backend_id"),
                "summary": f"HTTP backend `{backend.get('backend_id')}` returned {response.get('exit_code')}.",
                "url": call.get("url") or backend.get("url"),
                "method": method,
                **response,
            }

        if backend.get("kind") == "plugin":
            if action == "emit_artifact":
                target_path = call.get("path")
                if not target_path:
                    return {
                        "backend_id": backend.get("backend_id"),
                        "status": "failed",
                        "summary": f"Plugin backend `{backend.get('backend_id')}` missing artifact path.",
                        "stdout": "",
                        "stderr": "",
                        "exit_code": None,
                    }
                path = (root / target_path) if not Path(target_path).is_absolute() else Path(target_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                content = call.get("content", "")
                path.write_text(str(content), encoding="utf-8")
                return {
                    "backend_id": backend.get("backend_id"),
                    "status": "success",
                    "summary": f"Plugin backend `{backend.get('backend_id')}` wrote artifact `{path}`.",
                    "stdout": str(path),
                    "stderr": "",
                    "exit_code": 0,
                }
            if action in {"http_get", "http_post", "http_request"} and call.get("url"):
                method = call.get("method") or ("POST" if action == "http_post" else "GET")
                body = call.get("body")
                if "json_body" in call:
                    body = json.dumps(call.get("json_body"))
                response = _http_invoke(
                    call["url"],
                    method,
                    timeout_seconds,
                    headers=dict(call.get("headers", {})),
                    body=body,
                )
                return {
                    "backend_id": backend.get("backend_id"),
                    "summary": f"Plugin backend `{backend.get('backend_id')}` returned {response.get('exit_code')}.",
                    "url": call["url"],
                    "method": method,
                    **response,
                }
            return {
                "backend_id": backend.get("backend_id"),
                "status": "success",
                "summary": f"Plugin backend `{backend.get('backend_id')}` resolved.",
                "stdout": "",
                "stderr": "",
                "exit_code": 0,
            }

        return {
            "backend_id": backend.get("backend_id"),
            "status": "skipped",
            "summary": f"Backend `{backend.get('backend_id')}` is not directly invokable yet.",
            "stdout": "",
            "stderr": "",
            "exit_code": None,
        }


def request_from_payload(payload: dict) -> ExecutionRequest:
    return ExecutionRequest(
        task_id=payload.get("task_id") or f"task-{uuid.uuid4().hex[:10]}",
        task_family=payload["task_family"],
        description=payload.get("description", payload["task_family"]),
        quality_target=payload.get("quality_target", "balanced"),
        risk_level=payload.get("risk_level", "medium"),
        complexity=payload.get("complexity", "medium"),
        requires_code=bool(payload.get("requires_code", False)),
        requires_tools=bool(payload.get("requires_tools", False)),
        high_stakes=bool(payload.get("high_stakes", False)),
        force_expert=bool(payload.get("force_expert", False)),
        timeout_seconds=int(payload.get("timeout_seconds", 30)),
        workdir=payload.get("workdir"),
        owner_id=payload.get("owner_id", "brain"),
        approve_risky=bool(payload.get("approve_risky", False)),
        dispatch_mode=payload.get("dispatch_mode", "immediate"),
        queue_name=payload.get("queue_name"),
        not_before_at=payload.get("not_before_at"),
        max_retries=int(payload.get("max_retries", 1)),
        selected_executor_id=payload.get("selected_executor_id"),
        selected_router_id=payload.get("selected_router_id"),
        selected_backend_ids=list(payload.get("selected_backend_ids", [])),
        inputs=dict(payload.get("inputs", {})),
        bad_output=payload.get("bad_output"),
        expert_correction=payload.get("expert_correction"),
        verified_correction=bool(payload.get("verified_correction", False)),
    )


def _route_payload(request: ExecutionRequest) -> dict:
    return {
        "task_family": request.task_family,
        "quality_target": request.quality_target,
        "risk_level": request.risk_level,
        "complexity": request.complexity,
        "requires_code": request.requires_code,
        "requires_tools": request.requires_tools,
        "high_stakes": request.high_stakes,
        "force_expert": request.force_expert,
        "dispatch_mode": request.dispatch_mode,
    }


def _select_by_id(items: list[dict], id_field: str, identifier: str | None, default: dict | None) -> dict | None:
    if identifier is None:
        return default
    return next((item for item in items if item.get(id_field) == identifier), default)


def _risky_backend(backend: dict) -> bool:
    return bool(backend.get("destructive")) or backend.get("category") in {"cloud", "infra", "deployment"}


def _approval_required(request: ExecutionRequest, executor: dict | None, backends: list[dict]) -> tuple[bool, str]:
    if request.approve_risky:
        return False, "approved_by_request"
    if request.high_stakes or request.risk_level in {"high", "critical"}:
        return True, "high_risk_task"
    if executor and executor.get("supports_code") and request.requires_code and request.risk_level != "low":
        return True, "code_change_requires_review"
    if any(_risky_backend(backend) for backend in backends):
        return True, "risky_backend_selected"
    return False, "not_required"


def _queue_required(request: ExecutionRequest, executor: dict | None) -> bool:
    if request.dispatch_mode in {"deferred", "remote_worker"}:
        return True
    return bool(executor and executor.get("kind") == "remote_worker")


def _load_yaml_list(path: Path, key: str) -> tuple[dict, list[dict]]:
    payload = load_yaml_file(path)
    items = payload.setdefault(key, [])
    return payload, items


def _update_benchmarks(root: Path, request: ExecutionRequest, run: ExecutionRun, result: ExecutionResult) -> None:
    path = root / "capabilities" / "benchmarks.yaml"
    payload = load_yaml_file(path)
    payload.setdefault("task_family_benchmarks", [])
    payload.setdefault("model_benchmarks", [])
    payload.setdefault("agent_pair_metrics", [])
    payload.setdefault("agent_value_metrics", [])
    payload.setdefault("adapter_benchmarks", [])

    def upsert(items: list[dict], match_key: str, match_value: str, defaults: dict) -> dict:
        for item in items:
            if item.get(match_key) == match_value:
                return item
        items.append(defaults)
        return defaults

    task_metric = upsert(
        payload["task_family_benchmarks"],
        "task_family",
        request.task_family,
        {
            "task_family": request.task_family,
            "run_count": 0,
            "success_count": 0,
            "critic_pass_count": 0,
            "verified_execution_count": 0,
            "replay_candidate_count": 0,
            "avg_confidence": 0.0,
            "avg_latency_ms": 0.0,
            "avg_total_tokens": 0.0,
            "avg_prompt_tokens": 0.0,
            "avg_completion_tokens": 0.0,
            "avg_tool_context_tokens": 0.0,
            "queued_run_count": 0,
            "remote_dispatch_count": 0,
            "last_executor_id": run.selected_executor_id,
            "last_router_id": run.selected_router_id,
        },
    )
    task_metric["run_count"] += 1
    task_metric.setdefault("critic_pass_count", 0)
    task_metric.setdefault("verified_execution_count", 0)
    task_metric.setdefault("replay_candidate_count", 0)
    task_metric.setdefault("avg_latency_ms", 0.0)
    task_metric.setdefault("avg_total_tokens", 0.0)
    task_metric.setdefault("avg_prompt_tokens", 0.0)
    task_metric.setdefault("avg_completion_tokens", 0.0)
    task_metric.setdefault("avg_tool_context_tokens", 0.0)
    task_metric.setdefault("queued_run_count", 0)
    task_metric.setdefault("remote_dispatch_count", 0)
    task_metric["success_count"] += 1 if result.status == "success" else 0
    task_metric["critic_pass_count"] += 1 if result.critic_status == "passed" else 0
    task_metric["verified_execution_count"] += 1 if result.outputs.get("verified_execution", False) else 0
    task_metric["replay_candidate_count"] += 1 if result.outputs.get("replay_eligible", False) else 0
    prior_conf = float(task_metric.get("avg_confidence", 0.0))
    prior_latency = float(task_metric.get("avg_latency_ms", 0.0))
    prior_total_tokens = float(task_metric.get("avg_total_tokens", 0.0))
    prior_prompt_tokens = float(task_metric.get("avg_prompt_tokens", 0.0))
    prior_completion_tokens = float(task_metric.get("avg_completion_tokens", 0.0))
    prior_tool_context_tokens = float(task_metric.get("avg_tool_context_tokens", 0.0))
    count = max(1, int(task_metric["run_count"]))
    task_metric["avg_confidence"] = round(((prior_conf * (count - 1)) + result.confidence) / count, 4)
    task_metric["avg_latency_ms"] = round(((prior_latency * (count - 1)) + int(result.latency_ms)) / count, 2)
    task_metric["avg_total_tokens"] = round(
        ((prior_total_tokens * (count - 1)) + float(result.token_usage.get("total_tokens", 0))) / count,
        2,
    )
    task_metric["avg_prompt_tokens"] = round(
        ((prior_prompt_tokens * (count - 1)) + float(result.token_usage.get("prompt_tokens", 0))) / count,
        2,
    )
    task_metric["avg_completion_tokens"] = round(
        ((prior_completion_tokens * (count - 1)) + float(result.token_usage.get("completion_tokens", 0))) / count,
        2,
    )
    task_metric["avg_tool_context_tokens"] = round(
        ((prior_tool_context_tokens * (count - 1)) + float(result.token_usage.get("tool_context_tokens", 0))) / count,
        2,
    )
    task_metric["queued_run_count"] += 1 if request.dispatch_mode == "deferred" else 0
    task_metric["remote_dispatch_count"] += 1 if request.dispatch_mode == "remote_worker" else 0
    task_metric["last_executor_id"] = run.selected_executor_id
    task_metric["last_router_id"] = run.selected_router_id
    task_metric["updated_at"] = utc_now()

    if run.selected_router_id:
        model_metric = upsert(
            payload["model_benchmarks"],
            "model_id",
            run.selected_router_id,
            {
                "model_id": run.selected_router_id,
                "task_family": request.task_family,
                "run_count": 0,
                "success_count": 0,
                "critic_pass_count": 0,
                "avg_latency_ms": 0.0,
                "avg_total_tokens": 0.0,
                "last_used_at": None,
            },
        )
        model_metric.setdefault("critic_pass_count", 0)
        model_metric.setdefault("avg_latency_ms", 0.0)
        model_metric.setdefault("avg_total_tokens", 0.0)
        model_metric["run_count"] += 1
        model_metric["success_count"] += 1 if result.status == "success" else 0
        model_metric["critic_pass_count"] += 1 if result.critic_status == "passed" else 0
        model_metric["avg_latency_ms"] = round(
            ((float(model_metric.get("avg_latency_ms", 0.0)) * (model_metric["run_count"] - 1)) + int(result.latency_ms))
            / max(1, int(model_metric["run_count"])),
            2,
        )
        model_metric["avg_total_tokens"] = round(
            (
                (float(model_metric.get("avg_total_tokens", 0.0)) * (model_metric["run_count"] - 1))
                + float(result.token_usage.get("total_tokens", 0))
            )
            / max(1, int(model_metric["run_count"])),
            2,
        )
        model_metric["last_used_at"] = utc_now()

    if run.selected_executor_id:
        agent_metric = upsert(
            payload["agent_value_metrics"],
            "agent_id",
            run.selected_executor_id,
            {
                "agent_id": run.selected_executor_id,
                "task_family": request.task_family,
                "run_count": 0,
                "success_count": 0,
                "critic_failure_count": 0,
                "avg_confidence": 0.0,
                "avg_total_tokens": 0.0,
                "prune_protected": False,
            },
        )
        agent_metric["run_count"] += 1
        agent_metric.setdefault("critic_failure_count", 0)
        agent_metric.setdefault("avg_confidence", 0.0)
        agent_metric.setdefault("avg_latency_ms", 0.0)
        agent_metric.setdefault("avg_total_tokens", 0.0)
        agent_metric["success_count"] += 1 if result.status == "success" else 0
        agent_metric["critic_failure_count"] += 1 if result.critic_status == "failed" else 0
        agent_metric["avg_confidence"] = round(
            ((float(agent_metric.get("avg_confidence", 0.0)) * (agent_metric["run_count"] - 1)) + result.confidence)
            / max(1, int(agent_metric["run_count"])),
            4,
        )
        success_count = max(0, int(agent_metric["success_count"]))
        run_count = max(1, int(agent_metric["run_count"]))
        critic_failure_count = max(0, int(agent_metric["critic_failure_count"]))
        agent_metric["value_add_per_token"] = round(result.confidence, 4)
        total_tokens = max(1.0, float(result.token_usage.get("total_tokens", 0)))
        agent_metric["value_add_per_token"] = round((result.confidence * 1000.0) / total_tokens, 4)
        agent_metric["critic_rejection_rate"] = round(critic_failure_count / run_count, 4)
        agent_metric["ignored_edit_rate"] = 0.0
        agent_metric["avg_latency_ms"] = round(
            ((float(agent_metric.get("avg_latency_ms", 0.0)) * (run_count - 1)) + int(result.latency_ms)) / run_count,
            2,
        )
        agent_metric["avg_total_tokens"] = round(
            ((float(agent_metric.get("avg_total_tokens", 0.0)) * (run_count - 1)) + total_tokens) / run_count,
            2,
        )
        agent_metric["updated_at"] = utc_now()

    for backend_call in result.backend_calls:
        backend_id = backend_call.get("backend_id")
        if not backend_id:
            continue
        adapter_metric = upsert(
            payload["adapter_benchmarks"],
            "adapter_id",
            f"backend:{backend_id}:{request.task_family}",
            {
                "adapter_id": f"backend:{backend_id}:{request.task_family}",
                "task_family": request.task_family,
                "run_count": 0,
                "success_count": 0,
                "avg_latency_ms": 0.0,
                "avg_total_tokens": 0.0,
                "dispatch_mode": request.dispatch_mode,
                "last_status": None,
            },
        )
        adapter_metric.setdefault("avg_latency_ms", 0.0)
        adapter_metric.setdefault("avg_total_tokens", 0.0)
        adapter_metric["run_count"] += 1
        adapter_metric["success_count"] += 1 if backend_call.get("status") == "success" else 0
        adapter_metric["avg_latency_ms"] = round(
            ((float(adapter_metric.get("avg_latency_ms", 0.0)) * (adapter_metric["run_count"] - 1))
             + int(backend_call.get("latency_ms", result.latency_ms))) / max(1, int(adapter_metric["run_count"])),
            2,
        )
        adapter_metric["dispatch_mode"] = request.dispatch_mode
        adapter_metric["last_status"] = backend_call.get("status")
        adapter_metric["avg_total_tokens"] = round(
            (
                (float(adapter_metric.get("avg_total_tokens", 0.0)) * (adapter_metric["run_count"] - 1))
                + float(result.token_usage.get("total_tokens", 0))
            )
            / max(1, int(adapter_metric["run_count"])),
            2,
        )
        adapter_metric["updated_at"] = utc_now()

    payload["last_updated"] = datetime.now(timezone.utc).date().isoformat()
    dump_yaml_file(path, payload)


def _update_memory(root: Path, request: ExecutionRequest, run: ExecutionRun, result: ExecutionResult) -> None:
    facts_path = root / "memory" / "facts.yaml"
    conflicts_path = root / "memory" / "conflicts.yaml"
    facts_payload, facts = _load_yaml_list(facts_path, "facts")
    conflicts_payload, conflicts = _load_yaml_list(conflicts_path, "conflicts")

    if result.status != "success":
        return

    candidates = [
        {
            "subject": f"task_family:{request.task_family}",
            "predicate": "last_successful_executor",
            "object": run.selected_executor_id,
        },
        {
            "subject": f"task_family:{request.task_family}",
            "predicate": "last_successful_router",
            "object": run.selected_router_id,
        },
    ]
    for backend_id in run.selected_backend_ids:
        candidates.append(
            {
                "subject": f"backend:{backend_id}",
                "predicate": "last_seen_status",
                "object": "success",
            }
        )

    for candidate in candidates:
        if not candidate.get("object"):
            continue
        existing = next(
            (
                fact
                for fact in facts
                if fact.get("subject") == candidate["subject"] and fact.get("predicate") == candidate["predicate"]
            ),
            None,
        )
        if existing and existing.get("object") != candidate["object"]:
            conflicts.append(
                {
                    "conflict_id": f"conflict-{uuid.uuid4().hex[:10]}",
                    "subject": candidate["subject"],
                    "predicate": candidate["predicate"],
                    "previous_object": existing.get("object"),
                    "new_object": candidate["object"],
                    "detected_at": utc_now(),
                    "source_run_id": run.run_id,
                }
            )
        facts.append(
            {
                "fact_id": f"fact-{uuid.uuid4().hex[:10]}",
                "subject": candidate["subject"],
                "predicate": candidate["predicate"],
                "object": candidate["object"],
                "confidence": result.confidence,
                "source": run.run_id,
                "timestamp": utc_now(),
            }
        )

    facts_payload["last_updated"] = datetime.now(timezone.utc).date().isoformat()
    conflicts_payload["last_updated"] = datetime.now(timezone.utc).date().isoformat()
    dump_yaml_file(facts_path, facts_payload)
    dump_yaml_file(conflicts_path, conflicts_payload)


def _update_routes_and_triplets(root: Path, request: ExecutionRequest, run: ExecutionRun, result: ExecutionResult) -> None:
    path = root / "telemetry" / "routes.yaml"
    payload = load_yaml_file(path)
    routes = payload.setdefault("routes", [])
    triplets = payload.setdefault("training_triplets", [])

    route_record = {
        "task_id": request.task_id,
        "run_id": run.run_id,
        "task_family": request.task_family,
        "simulated": False,
        "status": result.status,
        "model_tier_path": result.route.get("model_tier_path", []),
        "executor_id": run.selected_executor_id,
        "router_id": run.selected_router_id,
        "backend_ids": run.selected_backend_ids,
        "dispatch_mode": request.dispatch_mode,
        "queue_name": request.queue_name,
        "quality_target": request.quality_target,
        "risk_level": request.risk_level,
        "confidence": result.confidence,
        "critic_status": result.critic_status,
        "verified_execution": result.outputs.get("verified_execution", False),
        "replay_eligible": result.outputs.get("replay_eligible", False),
        "replay_score": result.outputs.get("replay_score", 0.0),
        "latency_ms": int(result.latency_ms),
        "backend_success_count": len([call for call in result.backend_calls if call.get("status") == "success"]),
        "backend_failure_count": len([call for call in result.backend_calls if call.get("status") == "failed"]),
        "prompt_tokens": int(result.token_usage.get("prompt_tokens", 0)),
        "completion_tokens": int(result.token_usage.get("completion_tokens", 0)),
        "tool_context_tokens": int(result.token_usage.get("tool_context_tokens", 0)),
        "cache_read_tokens": int(result.token_usage.get("cache_read_tokens", 0)),
        "cache_write_tokens": int(result.token_usage.get("cache_write_tokens", 0)),
        "total_tokens": int(result.token_usage.get("total_tokens", 0)),
        "token_estimation_method": result.token_usage.get("estimation_method", "unknown"),
        "timestamp": utc_now(),
    }
    routes.append(route_record)

    if request.verified_correction and _material_change(request.bad_output, request.expert_correction):
        triplets.append(
            {
                "triplet_id": f"triplet-{uuid.uuid4().hex[:10]}",
                "task_family": request.task_family,
                "verified": True,
                "initial_prompt": request.description,
                "bad_output": request.bad_output,
                "expert_correction": request.expert_correction,
                "source_run_id": run.run_id,
                "timestamp": utc_now(),
            }
        )

    payload["last_updated"] = datetime.now(timezone.utc).date().isoformat()
    dump_yaml_file(path, payload)


def record_learning(root: Path, request: ExecutionRequest, run: ExecutionRun, result: ExecutionResult) -> None:
    ensure_state_files(root)
    _update_routes_and_triplets(root, request, run, result)
    _update_benchmarks(root, request, run, result)
    _update_memory(root, request, run, result)
    record_execution_acceptance(root, request, run, result)


def execute_request(repo_root: str | None, payload: dict, *, force_immediate: bool = False) -> dict:
    root = repo_root_from(repo_root)
    ensure_state_files(root)
    request = request_from_payload(payload)
    if force_immediate:
        request.dispatch_mode = "immediate"
        request.queue_name = None
        if request.selected_executor_id == "remote-worker":
            request.selected_executor_id = None
    runtime_registry = build_runtime_registry(root, write=True)
    route = plan_execution(root, _route_payload(request), runtime_registry=runtime_registry)
    blackboard = BlackboardStore(root)
    control_plane = ControlPlaneStore(root)

    executor = _select_by_id(
        runtime_registry.get("agent_executors", []),
        "executor_id",
        request.selected_executor_id,
        route.get("selected_executor"),
    )
    router = _select_by_id(
        runtime_registry.get("model_routers", []),
        "router_id",
        request.selected_router_id,
        route.get("selected_router"),
    )
    selected_backend_ids = request.selected_backend_ids or [backend.get("backend_id") for backend in route.get("backend_bundle", [])]
    backends = [
        backend
        for backend in runtime_registry.get("tool_backends", [])
        if backend.get("backend_id") in selected_backend_ids
    ]
    effective_route = {
        **route,
        "selected_executor": executor.get("executor_id") if executor else None,
        "selected_router": router.get("router_id") if router else None,
        "backend_bundle": backends,
    }

    task = {
        "task_id": request.task_id,
        "task_family": request.task_family,
        "description": request.description,
        "state": "queued",
        "approval_status": "not_required",
        "current_run_id": None,
        "dependencies": [],
        "updated_at": utc_now(),
        "created_at": utc_now(),
    }
    control_plane.upsert_task(task)

    leased, lease = control_plane.acquire_lease(request.task_id, request.owner_id)
    if not leased:
        return {
            "status": "blocked",
            "reason": "lease_held",
            "lease": lease,
        }

    run = ExecutionRun(
        run_id=f"run-{uuid.uuid4().hex[:12]}",
        task_id=request.task_id,
        status="running",
        selected_executor_id=executor.get("executor_id") if executor else None,
        selected_router_id=router.get("router_id") if router else None,
        selected_backend_ids=selected_backend_ids,
        dispatch_mode=request.dispatch_mode,
        queue_name=request.queue_name,
        current_step="routing",
        confidence=effective_route.get("confidence", 0.0),
    )
    control_plane.append_run(asdict(run))
    task["state"] = "running"
    task["current_run_id"] = run.run_id
    task["updated_at"] = utc_now()
    control_plane.upsert_task(task)

    blackboard.append_event(
        {
            "event_type": "task.created",
            "task_id": request.task_id,
            "agent_id": request.owner_id,
            "summary": request.description,
            "confidence": effective_route.get("confidence", 0.0),
            "user_goal": request.description,
            "timestamp": utc_now(),
        }
    )
    if router:
        blackboard.append_event(
            {
                "event_type": "model.selected",
                "task_id": request.task_id,
                "agent_id": request.owner_id,
                "summary": f"Selected router `{router.get('router_id')}`.",
                "confidence": effective_route.get("confidence", 0.0),
                "model_id": router.get("router_id"),
                "model_tier": ",".join(effective_route.get("model_tier_path", [])),
                "timestamp": utc_now(),
            }
        )

    approval_required, approval_reason = _approval_required(request, executor, backends)
    if approval_required:
        approval = control_plane.create_approval(request.task_id, run.run_id, approval_reason, request.risk_level, request.description)
        run.status = "awaiting_approval"
        run.approval_status = "pending"
        run.current_step = "approval"
        run.updated_at = utc_now()
        control_plane.append_run(asdict(run))
        task["state"] = "awaiting_approval"
        task["approval_status"] = "pending"
        task["updated_at"] = utc_now()
        control_plane.upsert_task(task)
        blackboard.append_event(
            {
                "event_type": "human.approval.required",
                "task_id": request.task_id,
                "agent_id": request.owner_id,
                "summary": f"Approval required for `{approval_reason}`.",
                "confidence": effective_route.get("confidence", 0.0),
                "reason": approval_reason,
                "risk_level": request.risk_level,
                "run_id": run.run_id,
                "approval_id": approval["approval_id"],
                "timestamp": utc_now(),
            }
        )
        control_plane.release_lease(request.task_id, request.owner_id)
        return {
            "status": "awaiting_approval",
            "run": asdict(run),
            "approval": approval,
            "route": effective_route,
        }

    if _queue_required(request, executor):
        queue_name = request.queue_name or ("remote-workers" if request.dispatch_mode == "remote_worker" else "deferred")
        run.queue_name = queue_name
        queue_item = control_plane.enqueue_request(
            task_id=request.task_id,
            run_id=run.run_id,
            payload=payload,
            dispatch_mode=request.dispatch_mode,
            queue_name=queue_name,
            not_before_at=request.not_before_at,
            max_attempts=request.max_retries,
        )
        run.status = "queued"
        run.current_step = "queued"
        run.updated_at = utc_now()
        control_plane.append_run(asdict(run))
        task["state"] = "queued"
        task["updated_at"] = utc_now()
        control_plane.upsert_task(task)
        control_plane.release_lease(request.task_id, request.owner_id)
        return {
            "status": "queued",
            "run": asdict(run),
            "queue_item": queue_item,
            "route": effective_route,
        }

    router_result = RouterAdapter().resolve(router, effective_route)
    run.current_step = "execution"
    run.updated_at = utc_now()
    control_plane.append_run(asdict(run))

    started = time.perf_counter()
    executor_result = ExecutorAdapter().invoke(root, executor or {}, request)
    backend_calls = []
    backend_adapter = BackendAdapter()
    for call in request.inputs.get("backend_requests", []):
        backend_id = call.get("backend_id")
        backend = next((item for item in backends if item.get("backend_id") == backend_id), None)
        if backend is None:
            backend_calls.append({"backend_id": backend_id, "status": "skipped", "summary": "Backend not selected."})
            continue
        call_started = time.perf_counter()
        backend_result = backend_adapter.invoke(root, backend, call)
        backend_result["latency_ms"] = int((time.perf_counter() - call_started) * 1000)
        backend_calls.append(backend_result)
    latency_ms = int((time.perf_counter() - started) * 1000)

    overall_success = executor_result.get("status") == "success" and all(
        call.get("status") in {"success", "skipped"} for call in backend_calls
    )
    critic_status = "passed" if overall_success else "failed"
    summary = executor_result.get("summary") or f"Task `{request.task_id}` executed."
    artifact_id = f"artifact-{uuid.uuid4().hex[:12]}"
    artifact = {
        "artifact_id": artifact_id,
        "task_id": request.task_id,
        "run_id": run.run_id,
        "kind": "execution_result",
        "summary": summary,
        "provenance": {
            "executor_id": run.selected_executor_id,
            "router_id": run.selected_router_id,
            "backend_ids": run.selected_backend_ids,
        },
        "critic_status": critic_status,
        "created_at": utc_now(),
    }
    control_plane.record_artifact(artifact)

    blackboard.append_event(
        {
            "event_type": "artifact.ready",
            "task_id": request.task_id,
            "agent_id": request.owner_id,
            "summary": summary,
            "confidence": effective_route.get("confidence", 0.0),
            "artifact_id": artifact_id,
            "model_tier": ",".join(effective_route.get("model_tier_path", [])),
            "critic_required": True,
            "next_step": "complete" if overall_success else "review",
            "dependencies_satisfied": True,
            "run_id": run.run_id,
            "timestamp": utc_now(),
        }
    )
    blackboard.append_event(
        {
            "event_type": f"critic.{critic_status}",
            "task_id": request.task_id,
            "agent_id": "critic",
            "summary": f"Critic {critic_status} for `{request.task_id}`.",
            "confidence": effective_route.get("confidence", 0.0),
            "artifact_id": artifact_id,
            "run_id": run.run_id,
            "failure_reasons": [] if critic_status == "passed" else [executor_result.get("failure_reason") or "backend_failure"],
            "timestamp": utc_now(),
        }
    )

    run.status = "completed" if overall_success else "failed"
    run.current_step = "complete"
    run.completed_at = utc_now()
    run.updated_at = utc_now()
    run.failure_reason = None if overall_success else executor_result.get("failure_reason") or "backend_failure"
    run.confidence = effective_route.get("confidence", 0.0)
    control_plane.append_run(asdict(run))
    task["state"] = run.status
    task["approval_status"] = run.approval_status
    task["updated_at"] = utc_now()
    control_plane.upsert_task(task)

    blackboard.append_event(
        {
            "event_type": "task.completed",
            "task_id": request.task_id,
            "agent_id": request.owner_id,
            "summary": summary,
            "confidence": effective_route.get("confidence", 0.0),
            "run_id": run.run_id,
            "status": run.status,
            "timestamp": utc_now(),
        }
    )

    result = ExecutionResult(
        status="success" if overall_success else "failed",
        summary=summary,
        stdout=executor_result.get("stdout", ""),
        stderr=executor_result.get("stderr", ""),
        exit_code=executor_result.get("exit_code"),
        backend_calls=backend_calls,
        artifacts=[artifact],
        confidence=effective_route.get("confidence", 0.0),
        failure_reason=run.failure_reason,
        route={
            "selected_executor": effective_route.get("selected_executor"),
            "selected_router": effective_route.get("selected_router"),
            "selected_backend_ids": [backend.get("backend_id") for backend in effective_route.get("backend_bundle", [])],
            "model_tier_path": effective_route.get("model_tier_path", []),
            "model_assignments": effective_route.get("model_assignments", {}),
            "router_resolution": router_result,
        },
        outputs={
            "replay_eligible": overall_success and critic_status == "passed",
            "verified_execution": overall_success and critic_status == "passed",
            "replay_score": round(min(1.0, effective_route.get("confidence", 0.0) * (1.0 if critic_status == "passed" else 0.5)), 4),
            "latency_ms": latency_ms,
            "executor_command": executor_result.get("command"),
        },
        critic_status=critic_status,
        latency_ms=latency_ms,
        token_usage=_collect_token_usage(request, executor_result, backend_calls, summary),
    )
    record_learning(root, request, run, result)
    control_plane.release_lease(request.task_id, request.owner_id)
    return {
        "status": result.status,
        "request": asdict(request),
        "run": asdict(run),
        "result": asdict(result),
        "route": effective_route,
    }
