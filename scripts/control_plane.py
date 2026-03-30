from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

try:
    from brain_utils import dump_yaml_file, file_lock, load_yaml_file, repo_root_from
except ModuleNotFoundError:
    from scripts.brain_utils import dump_yaml_file, file_lock, load_yaml_file, repo_root_from


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class BlackboardStore:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "telemetry" / "blackboard.yaml"
        self.lock_path = self.path.with_suffix(".lock")
        policies = load_yaml_file(root / "orchestrator" / "policies.yaml")
        self.required_fields = policies.get("blackboard_policy", {}).get("required_fields", [])
        self.event_types = set(policies.get("blackboard_policy", {}).get("event_types", []))

    def _load(self) -> dict:
        return load_yaml_file(self.path)

    def _write(self, payload: dict) -> None:
        payload["last_updated"] = datetime.now(timezone.utc).date().isoformat()
        dump_yaml_file(self.path, payload)

    def append_event(self, event: dict) -> dict:
        missing = [field for field in self.required_fields if field not in event]
        if missing:
            raise ValueError(f"Missing blackboard fields: {', '.join(sorted(missing))}")
        if event.get("event_type") not in self.event_types:
            raise ValueError(f"Unsupported blackboard event type: {event.get('event_type')}")
        with file_lock(self.lock_path):
            payload = self._load()
            events = payload.setdefault("events", [])
            events.append(event)
            self._write(payload)
        return event

    def query(self, *, task_id: str | None = None, event_type: str | None = None, run_id: str | None = None) -> list[dict]:
        events = self._load().get("events", [])
        results = []
        for event in events:
            if task_id is not None and event.get("task_id") != task_id:
                continue
            if event_type is not None and event.get("event_type") != event_type:
                continue
            if run_id is not None and event.get("run_id") != run_id:
                continue
            results.append(event)
        return results


class ControlPlaneStore:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "telemetry" / "control_plane.yaml"
        self.lock_path = self.path.with_suffix(".lock")

    def _load(self) -> dict:
        return load_yaml_file(self.path)

    def _write(self, payload: dict) -> None:
        payload["last_updated"] = datetime.now(timezone.utc).date().isoformat()
        dump_yaml_file(self.path, payload)

    def _upsert(self, key: str, identifier: str, item: dict, id_field: str) -> dict:
        with file_lock(self.lock_path):
            payload = self._load()
            items = payload.setdefault(key, [])
            for index, existing in enumerate(items):
                if existing.get(id_field) == identifier:
                    items[index] = item
                    self._write(payload)
                    return item
            items.append(item)
            self._write(payload)
        return item

    def get_items(self, key: str) -> list[dict]:
        return self._load().get(key, [])

    def get_task(self, task_id: str) -> dict | None:
        return next((item for item in self.get_items("tasks") if item.get("task_id") == task_id), None)

    def upsert_task(self, task: dict) -> dict:
        return self._upsert("tasks", task["task_id"], task, "task_id")

    def append_run(self, run: dict) -> dict:
        return self._upsert("runs", run["run_id"], run, "run_id")

    def get_run(self, run_id: str) -> dict | None:
        return next((item for item in self.get_items("runs") if item.get("run_id") == run_id), None)

    def get_approval(self, approval_id: str) -> dict | None:
        return next((item for item in self.get_items("approvals") if item.get("approval_id") == approval_id), None)

    def create_approval(self, task_id: str, run_id: str, reason: str, risk_level: str, summary: str) -> dict:
        approval = {
            "approval_id": f"approval-{uuid.uuid4().hex[:12]}",
            "task_id": task_id,
            "run_id": run_id,
            "state": "pending",
            "reason": reason,
            "risk_level": risk_level,
            "summary": summary,
            "created_at": utc_now(),
            "decided_at": None,
            "actor": None,
            "note": None,
        }
        return self._upsert("approvals", approval["approval_id"], approval, "approval_id")

    def record_approval_decision(self, approval_id: str, *, approved: bool, actor: str, note: str | None = None) -> dict | None:
        approval = next((item for item in self.get_items("approvals") if item.get("approval_id") == approval_id), None)
        if approval is None:
            return None
        approval["state"] = "approved" if approved else "rejected"
        approval["actor"] = actor
        approval["note"] = note
        approval["decided_at"] = utc_now()
        return self._upsert("approvals", approval_id, approval, "approval_id")

    def expire_stale_approvals(
        self,
        *,
        stale_after_minutes: int,
        actor: str = "brainstem-maintenance",
        note: str | None = None,
    ) -> list[dict]:
        expired: list[dict] = []
        with file_lock(self.lock_path):
            payload = self._load()
            approvals = payload.setdefault("approvals", [])
            runs = payload.setdefault("runs", [])
            tasks = payload.setdefault("tasks", [])
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(minutes=max(1, int(stale_after_minutes)))

            for approval in approvals:
                if approval.get("state") != "pending":
                    continue
                created_at = _parse_timestamp(approval.get("created_at"))
                if created_at is None or created_at > cutoff:
                    continue
                approval["state"] = "expired"
                approval["actor"] = actor
                approval["note"] = note or f"Expired after {stale_after_minutes} minutes without human approval."
                approval["decided_at"] = utc_now()
                expired.append(dict(approval))

                run = next((item for item in runs if item.get("run_id") == approval.get("run_id")), None)
                if run is not None:
                    run["status"] = "rejected"
                    run["approval_status"] = "expired"
                    run["current_step"] = "approval_expired"
                    run["failure_reason"] = "approval_expired"
                    run["completed_at"] = utc_now()
                    run["updated_at"] = utc_now()

                task = next((item for item in tasks if item.get("task_id") == approval.get("task_id")), None)
                if task is not None and task.get("approval_status") == "pending":
                    task["state"] = "approval_expired"
                    task["approval_status"] = "expired"
                    task["updated_at"] = utc_now()

            if expired:
                self._write(payload)
        return expired

    def record_artifact(self, artifact: dict) -> dict:
        return self._upsert("artifacts", artifact["artifact_id"], artifact, "artifact_id")

    def acquire_lease(self, task_id: str, owner_id: str, *, ttl_seconds: int = 300) -> tuple[bool, dict]:
        with file_lock(self.lock_path):
            payload = self._load()
            leases = payload.setdefault("leases", [])
            now = datetime.now(timezone.utc)
            active = []
            acquired = None

            for lease in leases:
                expires_at = _parse_timestamp(lease.get("lease_expires_at"))
                if expires_at and expires_at > now and lease.get("task_id") == task_id and lease.get("owner_id") != owner_id:
                    active.append(lease)
                elif expires_at and expires_at > now:
                    active.append(lease)

            if any(lease.get("task_id") == task_id and lease.get("owner_id") != owner_id for lease in active):
                holder = next(lease for lease in active if lease.get("task_id") == task_id and lease.get("owner_id") != owner_id)
                return False, holder

            acquired = {
                "task_id": task_id,
                "owner_id": owner_id,
                "lease_acquired_at": utc_now(),
                "lease_expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
            }
            active = [lease for lease in active if lease.get("task_id") != task_id]
            active.append(acquired)
            payload["leases"] = active
            self._write(payload)
            return True, acquired

    def release_lease(self, task_id: str, owner_id: str) -> None:
        with file_lock(self.lock_path):
            payload = self._load()
            leases = payload.setdefault("leases", [])
            payload["leases"] = [lease for lease in leases if not (lease.get("task_id") == task_id and lease.get("owner_id") == owner_id)]
            self._write(payload)

    def enqueue_request(
        self,
        *,
        task_id: str,
        run_id: str,
        payload: dict,
        dispatch_mode: str,
        queue_name: str,
        not_before_at: str | None = None,
        max_attempts: int = 1,
    ) -> dict:
        item = {
            "queue_item_id": f"queue-{uuid.uuid4().hex[:12]}",
            "task_id": task_id,
            "run_id": run_id,
            "dispatch_mode": dispatch_mode,
            "queue_name": queue_name,
            "state": "pending",
            "payload": payload,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "claimed_at": None,
            "completed_at": None,
            "worker_id": None,
            "linked_run_id": None,
            "last_error": None,
            "not_before_at": not_before_at,
            "attempt_count": 0,
            "max_attempts": max(1, int(max_attempts)),
        }
        return self._upsert("queue_items", item["queue_item_id"], item, "queue_item_id")

    def get_queue_items(
        self,
        *,
        state: str | None = None,
        dispatch_mode: str | None = None,
        queue_name: str | None = None,
    ) -> list[dict]:
        items = self.get_items("queue_items")
        results = []
        for item in items:
            if state is not None and item.get("state") != state:
                continue
            if dispatch_mode is not None and item.get("dispatch_mode") != dispatch_mode:
                continue
            if queue_name is not None and item.get("queue_name") != queue_name:
                continue
            results.append(item)
        return results

    def update_queue_item(self, queue_item_id: str, updates: dict) -> dict | None:
        existing = next((item for item in self.get_items("queue_items") if item.get("queue_item_id") == queue_item_id), None)
        if existing is None:
            return None
        existing.update(updates)
        existing["updated_at"] = utc_now()
        return self._upsert("queue_items", queue_item_id, existing, "queue_item_id")

    def get_queue_item(self, queue_item_id: str) -> dict | None:
        return next((item for item in self.get_items("queue_items") if item.get("queue_item_id") == queue_item_id), None)

    def mark_queue_item_dispatched(
        self,
        queue_item_id: str,
        *,
        worker_id: str,
        remote_ticket_id: str,
        transport_mode: str,
    ) -> dict | None:
        return self.update_queue_item(
            queue_item_id,
            {
                "state": "dispatched",
                "worker_id": worker_id,
                "remote_ticket_id": remote_ticket_id,
                "transport_mode": transport_mode,
                "dispatched_at": utc_now(),
                "last_error": None,
            },
        )

    def claim_queue_item(
        self,
        *,
        worker_id: str,
        queue_name: str | None = None,
        dispatch_mode: str | None = None,
    ) -> dict | None:
        with file_lock(self.lock_path):
            payload = self._load()
            items = payload.setdefault("queue_items", [])
            now = datetime.now(timezone.utc)
            claimed = None
            for item in items:
                if item.get("state") != "pending":
                    continue
                if dispatch_mode is not None and item.get("dispatch_mode") != dispatch_mode:
                    continue
                if queue_name is not None and item.get("queue_name") != queue_name:
                    continue
                not_before_at = _parse_timestamp(item.get("not_before_at"))
                if not_before_at and not_before_at > now:
                    continue
                claimed = item
                break
            if claimed is None:
                return None
            claimed["state"] = "claimed"
            claimed["worker_id"] = worker_id
            claimed["claimed_at"] = utc_now()
            claimed["updated_at"] = utc_now()
            claimed["attempt_count"] = int(claimed.get("attempt_count", 0)) + 1
            self._write(payload)
            return dict(claimed)

    def complete_queue_item(
        self,
        queue_item_id: str,
        *,
        state: str,
        linked_run_id: str | None = None,
        last_error: str | None = None,
    ) -> dict | None:
        existing = self.get_queue_item(queue_item_id)
        updates = {
            "state": state,
            "completed_at": utc_now() if state in {"completed", "failed"} else None,
            "linked_run_id": linked_run_id,
            "last_error": last_error,
        }
        updated = self.update_queue_item(queue_item_id, updates)
        if existing is not None:
            dispatch_run = self.get_run(existing.get("run_id"))
            if dispatch_run is not None:
                dispatch_run["status"] = state
                dispatch_run["current_step"] = "transport_complete" if state == "completed" else state
                dispatch_run["linked_run_id"] = linked_run_id
                dispatch_run["failure_reason"] = last_error
                dispatch_run["updated_at"] = utc_now()
                if state in {"completed", "failed"}:
                    dispatch_run["completed_at"] = utc_now()
                if state == "awaiting_approval":
                    dispatch_run["approval_status"] = "pending"
                self.append_run(dispatch_run)
        return updated

    def heartbeat_worker(
        self,
        *,
        worker_id: str,
        queue_name: str,
        dispatch_modes: list[str],
        status: str = "ready",
        worker_type: str = "local_scheduler",
        transport_mode: str = "local",
    ) -> dict:
        worker = {
            "worker_id": worker_id,
            "queue_name": queue_name,
            "dispatch_modes": dispatch_modes,
            "status": status,
            "worker_type": worker_type,
            "transport_mode": transport_mode,
            "last_heartbeat_at": utc_now(),
        }
        return self._upsert("workers", worker_id, worker, "worker_id")


def build_stores(repo_root: str | None = None) -> tuple[BlackboardStore, ControlPlaneStore]:
    root = repo_root_from(repo_root)
    return BlackboardStore(root), ControlPlaneStore(root)
