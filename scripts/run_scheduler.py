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


def _import_remote_results(control_plane: ControlPlaneStore, transport: RemoteFabricTransport) -> list[dict]:
    imported = []
    for result in transport.pending_results():
        status = result.get("status")
        if status == "success":
            terminal_state = "completed"
        elif status == "awaiting_approval":
            terminal_state = "awaiting_approval"
        else:
            terminal_state = "failed"
        control_plane.complete_queue_item(
            result["queue_item_id"],
            state=terminal_state,
            linked_run_id=result.get("linked_run_id"),
            last_error=result.get("reason"),
        )
        transport.archive_result(result["ticket_id"])
        imported.append(
            {
                "ticket_id": result["ticket_id"],
                "queue_item_id": result.get("queue_item_id"),
                "status": terminal_state,
                "linked_run_id": result.get("linked_run_id"),
            }
        )
    return imported


def _peek_remote_results(transport: RemoteFabricTransport) -> list[dict]:
    return [
        {
            "ticket_id": item.get("ticket_id"),
            "queue_item_id": item.get("queue_item_id"),
            "status": item.get("status"),
            "linked_run_id": item.get("linked_run_id"),
        }
        for item in transport.pending_results()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Process deferred and remote-worker queue items through the scheduler and selected transport backend.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--queue-name", default=None)
    parser.add_argument("--dispatch-mode", default=None)
    parser.add_argument("--worker-id", default="local-scheduler-worker")
    parser.add_argument("--process-limit", type=int, default=1)
    parser.add_argument("--transport-mode", default="auto", choices=["auto", "local", "fabric", "redis"])
    args = parser.parse_args()

    root = repo_root_from(args.repo_root)
    control_plane = ControlPlaneStore(root)
    preferred_transport = None if args.transport_mode == "auto" else args.transport_mode
    transport = RemoteFabricTransport(root, preferred_mode=preferred_transport)
    queue_name = args.queue_name or ("remote-workers" if args.dispatch_mode == "remote_worker" else "deferred")
    dispatch_modes = [args.dispatch_mode] if args.dispatch_mode else ["deferred", "remote_worker"]
    remote_dispatch = args.dispatch_mode == "remote_worker" or queue_name == "remote-workers"
    use_fabric = remote_dispatch and args.transport_mode != "local"
    worker = control_plane.heartbeat_worker(
        worker_id=args.worker_id,
        queue_name=queue_name,
        dispatch_modes=dispatch_modes,
        status="ready",
        worker_type="scheduler",
        transport_mode=transport.mode if use_fabric else "local",
    )

    if args.dry_run:
        eligible = control_plane.get_queue_items(state="pending", dispatch_mode=args.dispatch_mode, queue_name=args.queue_name)
        dump_json_stdout(
            {
                "worker": worker,
                "eligible_queue_items": len(eligible),
                "queue_name": args.queue_name,
                "dispatch_mode": args.dispatch_mode,
                "transport": transport.status(),
                "pending_remote_results": _peek_remote_results(transport),
            }
        )
        return 0

    imported_results = _import_remote_results(control_plane, transport)

    processed = []
    success = True
    for _ in range(max(1, int(args.process_limit))):
        item = control_plane.claim_queue_item(
            worker_id=args.worker_id,
            queue_name=args.queue_name,
            dispatch_mode=args.dispatch_mode,
        )
        if item is None:
            break
        if use_fabric and item.get("dispatch_mode") == "remote_worker":
            envelope = transport.dispatch(item)
            control_plane.mark_queue_item_dispatched(
                item["queue_item_id"],
                worker_id=args.worker_id,
                remote_ticket_id=envelope["ticket_id"],
                transport_mode=transport.mode,
            )
            processed.append(
                {
                    "queue_item_id": item["queue_item_id"],
                    "task_id": item.get("task_id"),
                    "status": "dispatched",
                    "remote_ticket_id": envelope["ticket_id"],
                }
            )
            continue
        payload = dict(item.get("payload", {}))
        payload["dispatch_mode"] = "immediate"
        payload["owner_id"] = args.worker_id
        if payload.get("selected_executor_id") == "remote-worker":
            payload["selected_executor_id"] = None
        result = execute_request(str(root), payload, force_immediate=True)
        if result.get("status") == "success":
            terminal_state = "completed"
        elif result.get("status") == "awaiting_approval":
            terminal_state = "awaiting_approval"
        else:
            terminal_state = "failed"
        control_plane.complete_queue_item(
            item["queue_item_id"],
            state=terminal_state,
            linked_run_id=result.get("run", {}).get("run_id"),
            last_error=result.get("reason") or result.get("result", {}).get("failure_reason"),
        )
        processed.append(
            {
                "queue_item_id": item["queue_item_id"],
                "task_id": item.get("task_id"),
                "status": result.get("status"),
                "linked_run_id": result.get("run", {}).get("run_id"),
            }
        )
        success = success and terminal_state in {"completed", "awaiting_approval"}

    dump_json_stdout(
        {
            "worker": worker,
            "transport": transport.status(),
            "imported_results": imported_results,
            "processed": processed,
            "count": len(processed),
        }
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
