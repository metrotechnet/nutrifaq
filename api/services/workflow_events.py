from __future__ import annotations

import threading
from datetime import datetime, timezone
from queue import Empty, Queue
from typing import Any

_subscribers_lock = threading.Lock()
_subscribers: set[Queue[dict[str, Any]]] = set()
_MAX_QUEUE_SIZE = 256


def subscribe_workflow_events() -> Queue[dict[str, Any]]:
    queue: Queue[dict[str, Any]] = Queue(maxsize=_MAX_QUEUE_SIZE)
    with _subscribers_lock:
        _subscribers.add(queue)
    return queue


def unsubscribe_workflow_events(queue: Queue[dict[str, Any]]) -> None:
    with _subscribers_lock:
        _subscribers.discard(queue)


def emit_workflow_event(event_type: str, payload: dict[str, Any] | None = None) -> None:
    event = {
        "type": str(event_type or "workflow.event"),
        "ts": datetime.now(timezone.utc).isoformat(),
        "payload": payload if isinstance(payload, dict) else {},
    }
    with _subscribers_lock:
        subscribers = list(_subscribers)
    for queue in subscribers:
        try:
            queue.put_nowait(event)
        except Exception:
            try:
                queue.get_nowait()
            except Empty:
                pass
            try:
                queue.put_nowait(event)
            except Exception:
                pass

