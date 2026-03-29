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


def build_stores(repo_root: str | None = None) -> tuple[BlackboardStore, ControlPlaneStore]:
    root = repo_root_from(repo_root)
    return BlackboardStore(root), ControlPlaneStore(root)
