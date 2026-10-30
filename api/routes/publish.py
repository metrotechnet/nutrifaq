from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.services.config import load_publish_log_entries, reset_publish_log_entries
from api.services.entra_auth_service import EntraUser, require_admin
from api.services.publish_scheduler import (
    cancel_scheduled_publish,
    get_publish_scheduler_status,
    schedule_publish,
)
from api.services.publish_service import cancel_publish, get_publish_status, start_publish, start_revert

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
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc), "message_key": "publish.schedule.invalid"},
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
    return cancel_publish()


@router.post("/api/publish/revert")
def revert_publish_api(_: EntraUser = Depends(require_admin)):
    """Restore the previous container state into the main container and resync Chroma."""
    return start_revert()


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
