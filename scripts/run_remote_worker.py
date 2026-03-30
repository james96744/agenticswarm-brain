from __future__ import annotations

import argparse

try:
    from brain_utils import dump_json_stdout, repo_root_from
    from control_plane import ControlPlaneStore
    from execution_engine import execute_request
    from remote_transport import RemoteFabricTransport
except ModuleNotFoundError:
    from scripts.brain_utils import dump_json_stdout, repo_root_from
    from scripts.control_plane import ControlPlaneStore
    from scripts.execution_engine import execute_request
    from scripts.remote_transport import RemoteFabricTransport


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll the selected remote-worker transport backend and execute dispatched jobs.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--worker-id", default="remote-fabric-worker")
    parser.add_argument("--queue-name", default="remote-workers")
    parser.add_argument("--process-limit", type=int, default=1)
    parser.add_argument("--transport-mode", default="auto", choices=["auto", "fabric", "redis"])
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    control_plane = ControlPlaneStore(root)
    preferred_transport = None if args.transport_mode == "auto" else args.transport_mode
    transport = RemoteFabricTransport(root, preferred_mode=preferred_transport)
    transport_worker = transport.heartbeat_worker(worker_id=args.worker_id, queue_name=args.queue_name, status="ready")
    control_plane_worker = control_plane.heartbeat_worker(
        worker_id=args.worker_id,
        queue_name=args.queue_name,
        dispatch_modes=["remote_worker"],
        status="ready",
        worker_type="remote_worker",
        transport_mode=transport.mode,
    )

    if args.dry_run:
        dump_json_stdout(
            {
                "transport_worker": transport_worker,
                "control_plane_worker": control_plane_worker,
                "transport": transport.status(),
            }
        )
        return 0

    processed = []
    success = True
    for _ in range(max(1, int(args.process_limit))):
        envelope = transport.claim(worker_id=args.worker_id, queue_name=args.queue_name)
        if envelope is None:
            break
        payload = dict(envelope.get("payload", {}))
        payload["dispatch_mode"] = "immediate"
        payload["owner_id"] = args.worker_id
        if payload.get("selected_executor_id") == "remote-worker":
            payload["selected_executor_id"] = None
        result = execute_request(str(root), payload, force_immediate=True)
        written = transport.write_result(envelope, result)
        processed.append(
            {
                "ticket_id": written["ticket_id"],
                "queue_item_id": written["queue_item_id"],
                "status": written["status"],
                "linked_run_id": written.get("linked_run_id"),
            }
        )
        success = success and result.get("status") in {"success", "awaiting_approval"}

    dump_json_stdout(
        {
            "transport_worker": transport_worker,
            "control_plane_worker": control_plane_worker,
            "transport": transport.status(),
            "processed": processed,
            "count": len(processed),
        }
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
