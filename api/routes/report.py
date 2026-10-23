"""
Report API Routes

This module defines endpoints for logging user feedback (comments, likes) and serving log files in the Nutrifaq Agent backend.
"""
from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pathlib import Path
import os

from api.services.entra_auth_service import EntraUser, require_admin, require_collaborator
from api.services.logging import add_comment_to_question, add_like_to_question, _download_log_from_gcs, reset_question_log
from api.services.log_viewer_service import clear_log_file, get_log_metadata, read_log_text, resolve_log_path

router = APIRouter()

PROJECT_ROOT = Path(__file__).parent.parent.parent
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))



@router.post("/api/add_comment")
def add_comment_api(
    question_id: str = Body(...),
    comment: str = Body(...)
):
    """
    Add a user comment to a specific question in the log.

    Args:
        question_id (str): The ID of the question to comment on.
        comment (str): The comment text.

    Returns:
        dict: Status and message indicating success or error.
    """
    success = add_comment_to_question(question_id, comment)
    if success:
        return {"status": "success", "message": "Comment added"}
    else:
        return {"status": "error", "message": "Question ID not found"}


@router.post("/api/reset_question_log")
def reset_question_log_api(user: EntraUser = Depends(require_collaborator)):
    """Reset the question log for the current logged-in user session."""
    del user
    return {"status": "success", "entries": reset_question_log()}



@router.post("/api/like_answer")
def like_answer(
    question_id: str = Body(...),
    like: bool = Body(...)
):
    """
    Add or update a like/dislike vote for a question. Replaces any previous vote.

    Args:
        question_id (str): The ID of the question to like/dislike.
        like (bool): True for like, False for dislike.

    Returns:
        dict: Updated like/dislike status for the question.
    """
    return add_like_to_question(question_id, like)


@router.get("/api/download_log")

@router.get("/api/download_log")
def download_question_log(_: EntraUser = Depends(require_admin), key: str = Query(None)):
    """
    Download the full questions log as a JSON file (admin access).

    Args:
        key (str): Admin key for authorization.

    Returns:
        FileResponse or dict: The log file or error message.
    """
    data = _download_log_from_gcs()
    if not data:
        return {"status": "error", "message": "Log file not found"}
    return JSONResponse(
        content=data,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=question_log.json"}
    )



@router.get("/api/logs/view")
def get_log_view(_: EntraUser = Depends(require_admin)):
    """Return the current log file content for the admin log viewer."""
    payload = {
        "status": "ok",
        "content": read_log_text(),
        "metadata": get_log_metadata(),
    }
    return payload


@router.post("/api/logs/clear")
def clear_log_view(_: EntraUser = Depends(require_admin)):
    """Clear the runtime log file and return the empty view."""
    clear_log_file()
    return {
        "status": "success",
        "content": "",
        "metadata": get_log_metadata(),
    }


@router.get("/api/logs/download")
def download_log_text(_: EntraUser = Depends(require_admin)):
    """Download the current log file as plain text."""
    content = read_log_text()
    file_name = resolve_log_path().name
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={file_name}"},
    )


@router.get("/log_report", response_class=HTMLResponse)
def serve_log_report(request: Request):
    """
    Serve the HTML log report page.
    
    The page itself is public, but all API calls from the page require a valid bearer token.
    The token is passed via URL query parameter and must be included in fetch Authorization headers.
    """
    return templates.TemplateResponse("log_report.html", {"request": request})
