from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import uuid

try:
    from brain_utils import load_yaml_file, repo_root_from
except ModuleNotFoundError:
    from scripts.brain_utils import load_yaml_file, repo_root_from


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class _FilesystemTransport:
    def __init__(self, root: Path, config: dict):
        fabric_root = Path(config.get("fabric_root", "telemetry/remote_fabric"))
        if not fabric_root.is_absolute():
            fabric_root = root / fabric_root
        self.mode = "shared_filesystem_fabric"
        self.fabric_root = fabric_root
        self.inbox_dir = self.fabric_root / "inbox"
        self.claims_dir = self.fabric_root / "claims"
        self.results_dir = self.fabric_root / "results"
        self.archive_dir = self.fabric_root / "archive"
        self.workers_dir = self.fabric_root / "workers"
        for directory in (self.inbox_dir, self.claims_dir, self.results_dir, self.archive_dir, self.workers_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def status(self) -> dict:
        return {
            "mode": self.mode,
            "backend": "filesystem",
            "available": True,
            "fabric_root": str(self.fabric_root),
            "inbox": len(list(self.inbox_dir.glob("*.json"))),
            "claims": len(list(self.claims_dir.glob("*.json"))),
            "results": len(list(self.results_dir.glob("*.json"))),
            "workers": len(list(self.workers_dir.glob("*.json"))),
        }

    def dispatch(self, queue_item: dict) -> dict:
        ticket_id = f"ticket-{uuid.uuid4().hex[:12]}"
        envelope = {
            "ticket_id": ticket_id,
            "queue_item_id": queue_item.get("queue_item_id"),
            "task_id": queue_item.get("task_id"),
            "dispatch_run_id": queue_item.get("run_id"),
            "dispatch_mode": queue_item.get("dispatch_mode"),
            "queue_name": queue_item.get("queue_name"),
            "payload": queue_item.get("payload", {}),
            "state": "pending",
            "created_at": utc_now(),
            "claimed_at": None,
            "completed_at": None,
            "worker_id": None,
        }
        _atomic_json_write(self.inbox_dir / f"{ticket_id}.json", envelope)
        return envelope

    def claim(self, *, worker_id: str, queue_name: str | None = None) -> dict | None:
        for path in sorted(self.inbox_dir.glob("*.json")):
            try:
                envelope = _load_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            if queue_name is not None and envelope.get("queue_name") != queue_name:
                continue
            claim_path = self.claims_dir / path.name
            try:
                os.replace(path, claim_path)
            except OSError:
                continue
            envelope["state"] = "claimed"
            envelope["claimed_at"] = utc_now()
            envelope["worker_id"] = worker_id
            _atomic_json_write(claim_path, envelope)
            return envelope
        return None

    def write_result(self, envelope: dict, result: dict) -> dict:
        ticket_id = envelope["ticket_id"]
        payload = {
            "ticket_id": ticket_id,
            "queue_item_id": envelope.get("queue_item_id"),
            "task_id": envelope.get("task_id"),
            "dispatch_run_id": envelope.get("dispatch_run_id"),
            "worker_id": envelope.get("worker_id"),
            "status": result.get("status"),
            "linked_run_id": result.get("run", {}).get("run_id"),
            "reason": result.get("reason") or result.get("result", {}).get("failure_reason"),
            "completed_at": utc_now(),
        }
        _atomic_json_write(self.results_dir / f"{ticket_id}.json", payload)
        claim_path = self.claims_dir / f"{ticket_id}.json"
        if claim_path.exists():
            os.replace(claim_path, self.archive_dir / f"{ticket_id}.claim.json")
        return payload

    def pending_results(self) -> list[dict]:
        results = []
        for path in sorted(self.results_dir.glob("*.json")):
            try:
                payload = _load_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            payload["_path"] = str(path)
            results.append(payload)
        return results

    def archive_result(self, ticket_id: str) -> None:
        path = self.results_dir / f"{ticket_id}.json"
        if not path.exists():
            return
        os.replace(path, self.archive_dir / f"{ticket_id}.result.json")

    def heartbeat_worker(
        self,
        *,
        worker_id: str,
        queue_name: str,
        status: str = "ready",
        worker_type: str = "remote_worker",
    ) -> dict:
        payload = {
            "worker_id": worker_id,
            "queue_name": queue_name,
            "status": status,
            "worker_type": worker_type,
            "transport_mode": self.mode,
            "last_heartbeat_at": utc_now(),
        }
        _atomic_json_write(self.workers_dir / f"{worker_id}.json", payload)
        return payload


class _RedisTransport:
    def __init__(self, config: dict):
        self.mode = "redis_broker"
        self._config = config
        self._redis = None
        self._reason = None
        self._url = None
        self._prefix = None
        redis_config = config.get("redis", {})
        url_env_var = redis_config.get("url_env_var", "REDIS_URL")
        self._url = os.environ.get(url_env_var) or redis_config.get("url")
        self._prefix = redis_config.get("queue_prefix", "agenticswarm-brain")
        try:
            import redis  # type: ignore
        except ImportError:
            self._reason = "python_redis_package_not_installed"
            return
        if not self._url:
            self._reason = f"missing_{url_env_var}"
            return
        try:
            client = redis.Redis.from_url(self._url, decode_responses=True)
            client.ping()
            self._redis = client
        except Exception as exc:  # pragma: no cover - environment-specific
            self._reason = f"redis_unavailable:{exc}"

    @property
    def available(self) -> bool:
        return self._redis is not None

    def _require(self):
        if self._redis is None:
            raise RuntimeError(self._reason or "redis_transport_unavailable")
        return self._redis

    def _pending_key(self, queue_name: str) -> str:
        return f"{self._prefix}:queue:{queue_name}:pending"

    def _results_key(self, queue_name: str) -> str:
        return f"{self._prefix}:queue:{queue_name}:results"

    def _claim_key(self, ticket_id: str) -> str:
        return f"{self._prefix}:claim:{ticket_id}"

    def _result_payload_key(self, ticket_id: str) -> str:
        return f"{self._prefix}:result:{ticket_id}"

    def _worker_key(self, worker_id: str) -> str:
        return f"{self._prefix}:worker:{worker_id}"

    def _archive_claim_key(self, ticket_id: str) -> str:
        return f"{self._prefix}:archive:claim:{ticket_id}"

    def _archive_result_key(self, ticket_id: str) -> str:
        return f"{self._prefix}:archive:result:{ticket_id}"

    def status(self) -> dict:
        if not self.available:
            return {
                "mode": self.mode,
                "backend": "redis",
                "available": False,
                "reason": self._reason,
                "url": self._url,
                "queue_prefix": self._prefix,
                "inbox": 0,
                "claims": 0,
                "results": 0,
                "workers": 0,
            }
        client = self._require()
        try:
            pending = 0
            results = 0
            for key in client.scan_iter(match=f"{self._prefix}:queue:*:pending"):
                pending += int(client.llen(key))
            for key in client.scan_iter(match=f"{self._prefix}:queue:*:results"):
                results += int(client.llen(key))
            claims = sum(1 for _ in client.scan_iter(match=f"{self._prefix}:claim:*"))
            workers = sum(1 for _ in client.scan_iter(match=f"{self._prefix}:worker:*"))
        except Exception as exc:  # pragma: no cover - environment-specific
            return {
                "mode": self.mode,
                "backend": "redis",
                "available": False,
                "reason": f"redis_status_failed:{exc}",
                "url": self._url,
                "queue_prefix": self._prefix,
                "inbox": 0,
                "claims": 0,
                "results": 0,
                "workers": 0,
            }
        return {
            "mode": self.mode,
            "backend": "redis",
            "available": True,
            "url": self._url,
            "queue_prefix": self._prefix,
            "inbox": pending,
            "claims": claims,
            "results": results,
            "workers": workers,
        }

    def dispatch(self, queue_item: dict) -> dict:
        client = self._require()
        ticket_id = f"ticket-{uuid.uuid4().hex[:12]}"
        envelope = {
            "ticket_id": ticket_id,
            "queue_item_id": queue_item.get("queue_item_id"),
            "task_id": queue_item.get("task_id"),
            "dispatch_run_id": queue_item.get("run_id"),
            "dispatch_mode": queue_item.get("dispatch_mode"),
            "queue_name": queue_item.get("queue_name"),
            "payload": queue_item.get("payload", {}),
            "state": "pending",
            "created_at": utc_now(),
            "claimed_at": None,
            "completed_at": None,
            "worker_id": None,
        }
        client.rpush(self._pending_key(envelope.get("queue_name") or "remote-workers"), json.dumps(envelope, sort_keys=True))
        return envelope

    def claim(self, *, worker_id: str, queue_name: str | None = None) -> dict | None:
        client = self._require()
        key = self._pending_key(queue_name or "remote-workers")
        raw = client.lpop(key)
        if not raw:
            return None
        envelope = json.loads(raw)
        envelope["state"] = "claimed"
        envelope["claimed_at"] = utc_now()
        envelope["worker_id"] = worker_id
        client.set(self._claim_key(envelope["ticket_id"]), json.dumps(envelope, sort_keys=True))
        return envelope

    def write_result(self, envelope: dict, result: dict) -> dict:
        client = self._require()
        ticket_id = envelope["ticket_id"]
        payload = {
            "ticket_id": ticket_id,
            "queue_item_id": envelope.get("queue_item_id"),
            "task_id": envelope.get("task_id"),
            "dispatch_run_id": envelope.get("dispatch_run_id"),
            "worker_id": envelope.get("worker_id"),
            "status": result.get("status"),
            "linked_run_id": result.get("run", {}).get("run_id"),
            "reason": result.get("reason") or result.get("result", {}).get("failure_reason"),
            "completed_at": utc_now(),
            "queue_name": envelope.get("queue_name"),
        }
        client.set(self._result_payload_key(ticket_id), json.dumps(payload, sort_keys=True))
        client.rpush(self._results_key(envelope.get("queue_name") or "remote-workers"), ticket_id)
        claim_payload = client.get(self._claim_key(ticket_id))
        if claim_payload is not None:
            client.set(self._archive_claim_key(ticket_id), claim_payload)
            client.delete(self._claim_key(ticket_id))
        return payload

    def pending_results(self) -> list[dict]:
        client = self._require()
        results: list[dict] = []
        for key in client.scan_iter(match=f"{self._prefix}:queue:*:results"):
            queue_name = key.rsplit(":", 1)[0].split(":queue:", 1)[1]
            for ticket_id in client.lrange(key, 0, -1):
                payload = client.get(self._result_payload_key(ticket_id))
                if payload is None:
                    continue
                item = json.loads(payload)
                item["queue_name"] = queue_name
                results.append(item)
        return results

    def archive_result(self, ticket_id: str) -> None:
        client = self._require()
        payload = client.get(self._result_payload_key(ticket_id))
        if payload is None:
            return
        item = json.loads(payload)
        queue_name = item.get("queue_name") or "remote-workers"
        client.lrem(self._results_key(queue_name), 1, ticket_id)
        client.set(self._archive_result_key(ticket_id), payload)
        client.delete(self._result_payload_key(ticket_id))

    def heartbeat_worker(
        self,
        *,
        worker_id: str,
        queue_name: str,
        status: str = "ready",
        worker_type: str = "remote_worker",
    ) -> dict:
        client = self._require()
        payload = {
            "worker_id": worker_id,
            "queue_name": queue_name,
            "status": status,
            "worker_type": worker_type,
            "transport_mode": self.mode,
            "last_heartbeat_at": utc_now(),
        }
        client.set(self._worker_key(worker_id), json.dumps(payload, sort_keys=True), ex=600)
        return payload


class RemoteFabricTransport:
    def __init__(self, root: Path, *, preferred_mode: str | None = None):
        self.root = root
        policies = load_yaml_file(root / "orchestrator" / "policies.yaml")
        self.config = policies.get("remote_worker_policy", {})
        self.packaging_profile = policies.get("packaging_profile", {})
        self.active_tier = self.packaging_profile.get("active_tier", "community")
        self.tier_config = self.packaging_profile.get("tiers", {}).get(self.active_tier, {})
        self.allow_local_fallback = bool(self.config.get("allow_local_fallback", True))
        self.requested_mode = self._normalize_mode(preferred_mode or self.config.get("transport_mode", "shared_filesystem_fabric"))
        self.restriction_reason = None
        self.backend = self._build_backend()
        self.mode = self.backend.mode

    def _normalize_mode(self, mode: str) -> str:
        aliases = {
            "fabric": "shared_filesystem_fabric",
            "filesystem": "shared_filesystem_fabric",
            "shared_filesystem_fabric": "shared_filesystem_fabric",
            "redis": "redis_broker",
            "broker": "redis_broker",
            "redis_broker": "redis_broker",
            "auto": self.config.get("transport_mode", "shared_filesystem_fabric"),
        }
        return aliases.get(mode, mode)

    def _build_backend(self):
        allowed_modes = set(self.tier_config.get("allowed_remote_transport_modes", ["shared_filesystem_fabric"]))
        default_mode = self._normalize_mode(self.tier_config.get("default_remote_transport_mode", "shared_filesystem_fabric"))
        if self.requested_mode not in allowed_modes:
            self.restriction_reason = f"transport_mode_{self.requested_mode}_not_allowed_for_{self.active_tier}"
            self.requested_mode = default_mode
        if self.requested_mode == "redis_broker":
            redis_backend = _RedisTransport(self.config)
            if redis_backend.available:
                return redis_backend
            if not self.allow_local_fallback:
                return redis_backend
            filesystem = _FilesystemTransport(self.root, self.config)
            filesystem.fallback_reason = redis_backend.status().get("reason")
            return filesystem
        return _FilesystemTransport(self.root, self.config)

    def status(self) -> dict:
        payload = self.backend.status()
        payload["packaging_tier"] = self.active_tier
        payload["requested_mode"] = self.requested_mode
        payload["active_mode"] = self.backend.mode
        payload["allowed_modes"] = self.tier_config.get("allowed_remote_transport_modes", ["shared_filesystem_fabric"])
        if self.restriction_reason:
            payload["restriction_reason"] = self.restriction_reason
        if getattr(self.backend, "fallback_reason", None):
            payload["fallback_reason"] = self.backend.fallback_reason
        return payload

    def dispatch(self, queue_item: dict) -> dict:
        return self.backend.dispatch(queue_item)

    def claim(self, *, worker_id: str, queue_name: str | None = None) -> dict | None:
        return self.backend.claim(worker_id=worker_id, queue_name=queue_name)

    def write_result(self, envelope: dict, result: dict) -> dict:
        return self.backend.write_result(envelope, result)

    def pending_results(self) -> list[dict]:
        return self.backend.pending_results()

    def archive_result(self, ticket_id: str) -> None:
        self.backend.archive_result(ticket_id)

    def heartbeat_worker(
        self,
        *,
        worker_id: str,
        queue_name: str,
        status: str = "ready",
        worker_type: str = "remote_worker",
    ) -> dict:
        return self.backend.heartbeat_worker(
            worker_id=worker_id,
            queue_name=queue_name,
            status=status,
            worker_type=worker_type,
        )


def build_remote_transport(repo_root: str | None = None, *, preferred_mode: str | None = None) -> RemoteFabricTransport:
    return RemoteFabricTransport(repo_root_from(repo_root), preferred_mode=preferred_mode)
