from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.services.entra_auth_service import EntraUser, require_admin
from api.services.publish_scheduler import get_scheduled_jobs, schedule_publish

router = APIRouter()


class PublishRequest(BaseModel):
    model: str
    provider: str | None = None
    publish_at: str


@router.post("/api/publish")
def schedule_publish_api(
    payload: PublishRequest,
    _: EntraUser = Depends(require_admin),
):
    """Queue a scheduled publication job from the debug KB to the production KB."""
    try:
        publish_dt = datetime.fromisoformat(payload.publish_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid publish_at timestamp: {payload.publish_at}") from exc

    try:
        job = schedule_publish(
            model=payload.model,
            provider=payload.provider,
            publish_at=publish_dt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to schedule publication: {exc}") from exc

    return {"status": "ok", "job": job}


@router.get("/api/publish/jobs")
def list_publish_jobs(_: EntraUser = Depends(require_admin)):
    """List scheduled publish jobs."""
    return {"status": "ok", "jobs": get_scheduled_jobs()}
