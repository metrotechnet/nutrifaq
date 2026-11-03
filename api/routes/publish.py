from __future__ import annotations

import asyncio
import json
from queue import Empty
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from api.services.config import load_publish_log_entries, reset_publish_log_entries
from api.services.entra_auth_service import EntraUser, require_admin
from api.services.publish_scheduler import (
    cancel_scheduled_publish,
    clear_active_publish_schedule_on_cancel,
    get_publish_scheduler_status,
    schedule_publish,
)
from api.services.publish_service import cancel_publish, get_publish_status, start_revert
from api.services.workflow_events import subscribe_workflow_events, unsubscribe_workflow_events

router = APIRouter()


class PublishRequest(BaseModel):
    model: str
    provider: str | None = None


@router.post("/api/publish")
def publish_now_api(
    payload: PublishRequest,
    _: EntraUser = Depends(require_admin),
):
    """Start the publication workflow in the background."""
    model = str(payload.model or "").strip()
    if not model:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "A model is required for publication.",
                "message_key": "publish.status.modelRequired",
            },
        )

    provider = str(payload.provider or "azure").strip() or "azure"
    try:
        return schedule_publish(
            model=model,
            provider=provider,
            publish_at=datetime.now(timezone.utc).isoformat(),
            recurrence="once",
            timezone_name="UTC",
            job_id="live-publish",
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc), "message_key": "publish.status.invalid"},
        )


class PublishScheduleRequest(BaseModel):
    model: str
    provider: str | None = "azure"
    run_at: str | None = None
    cron: str | None = None
    interval_minutes: int | None = None
    user_time: str | None = None
    recurrence: str | None = None
    timezone_name: str | None = "UTC"
    job_id: str | None = None


@router.post("/api/publish/schedule")
def schedule_publish_api(
    payload: PublishScheduleRequest,
    _: EntraUser = Depends(require_admin),
):
    """Create a one-time or recurring automated publish schedule."""
    model = str(payload.model or "").strip()
    if not model:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "A model is required to schedule publication.",
                "message_key": "publish.schedule.modelRequired",
            },
        )

    try:
        return schedule_publish(
            model=model,
            provider=str(payload.provider or "azure").strip() or "azure",
            publish_at=payload.run_at,
            cron=payload.cron,
            interval_minutes=payload.interval_minutes,
            user_time=payload.user_time,
            recurrence=payload.recurrence,
            timezone_name=str(payload.timezone_name or "UTC").strip() or "UTC",
            job_id=payload.job_id or "active-publish-schedule",
        )
    except ValueError as exc:
        status_code = 409 if "already running" in str(exc).lower() else 400
        message_key = "publish.schedule.busy" if status_code == 409 else "publish.schedule.invalid"
        return JSONResponse(
            status_code=status_code,
            content={"status": "error", "message": str(exc), "message_key": message_key},
        )


@router.get("/api/publish/schedule/status")
def publish_scheduler_status(_: EntraUser = Depends(require_admin)):
    """Return scheduler + processing status for frontend polling orchestration."""
    return get_publish_scheduler_status()


@router.delete("/api/publish/schedule/{job_id}")
def delete_publish_schedule(job_id: str, _: EntraUser = Depends(require_admin)):
    """Delete a scheduled automatic publish."""
    return cancel_scheduled_publish(job_id)


@router.post("/api/publish/cancel")
def cancel_publish_api(_: EntraUser = Depends(require_admin)):
    """Request cancellation of the current publish or revert job."""
    cancel_result = cancel_publish()
    schedule_cleanup = clear_active_publish_schedule_on_cancel()
    if isinstance(cancel_result, dict):
        cancel_result["schedule"] = schedule_cleanup
    return cancel_result


@router.post("/api/publish/revert")
def revert_publish_api(_: EntraUser = Depends(require_admin)):
    """Restore the previous container state into the main container and resync Chroma."""
    return start_revert()


@router.get("/api/workflow/events")
async def workflow_events_stream(
    request: Request,
    _: EntraUser = Depends(require_admin),
):
    """Stream real-time workflow events to the frontend."""

    subscriber = subscribe_workflow_events()

    async def _stream():
        try:
            hello_payload: dict[str, object] = {}
            try:
                publish_status_snapshot = get_publish_status()
                hello_payload = {
                    "schedule_status": get_publish_scheduler_status(),
                    "publish_status": publish_status_snapshot,
                    "indexing_status": publish_status_snapshot.get("indexation", {}),
                }
            except Exception:
                hello_payload = {}
            hello = {"type": "workflow.connected", "ts": datetime.now(timezone.utc).isoformat(), "payload": hello_payload}
            yield f"event: {hello['type']}\ndata: {json.dumps(hello, ensure_ascii=False)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.to_thread(subscriber.get, True, 15.0)
                except Empty:
                    yield ": keep-alive\n\n"
                    continue
                event_type = str(event.get("type") or "workflow.event")
                yield f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            unsubscribe_workflow_events(subscriber)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/publish/status")
def publish_status(_: EntraUser = Depends(require_admin)):
    """Return current publish job status and progress."""
    return get_publish_status()


@router.get("/api/publish/log")
def list_publish_log(_: EntraUser = Depends(require_admin)):
    """Return publish log entries stored in nutrifaq-config blob."""
    try:
        return {"status": "ok", "entries": load_publish_log_entries()}
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Unable to read publish log: {exc}",
                "message_key": "publish.logs.error",
            },
        )


@router.post("/api/publish/log/reset")
def reset_publish_log(_: EntraUser = Depends(require_admin)):
    """Reset publish log entries stored in nutrifaq-config blob."""
    try:
        entries = reset_publish_log_entries()
        return {"status": "ok", "entries": entries}
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Unable to reset publish log: {exc}",
                "message_key": "publish.logs.resetError",
            },
        )
