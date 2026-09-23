from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.services.config import load_publish_log_entries, reset_publish_log_entries
from api.services.entra_auth_service import EntraUser, require_admin
from api.services.publish_service import get_publish_status, start_publish, start_revert

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

    provider = str(payload.provider or "vercel").strip() or "vercel"
    return start_publish(model=model, provider=provider)


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
