"""
Update API Routes

This module defines endpoints for triggering the Google Drive document indexing pipeline in the Nutria Agent backend.
Update API Routes

This module defines endpoints for triggering the Google Drive document indexing pipeline in the Nutria Agent backend.
"""
from fastapi import APIRouter, Request, Query
from datetime import datetime
from typing import Optional


router = APIRouter()
from api.update_gdrive import run_pipeline


@router.post("/update")
def update_pipeline(request: Request, agent: Optional[str] = Query(default="agent", description="Agent/Knowledge base to update")):
    """
    Trigger the Google Drive document indexing pipeline for the Nutria Agent.

    This endpoint is typically called by Cloud Scheduler daily at 3 AM.

    Trigger the Google Drive document indexing pipeline for the Nutria Agent.

    This endpoint is typically called by Cloud Scheduler daily at 3 AM.

    Args:
        request (Request): FastAPI request object.
        agent (str, optional): Agent/knowledge base identifier (default: 'agent').

    Returns:
        dict: Status and message about the pipeline execution.
        request (Request): FastAPI request object.
        agent (str, optional): Agent/knowledge base identifier (default: 'agent').

    Returns:
        dict: Status and message about the pipeline execution.
    """
    try:
        print(f"[{datetime.now().isoformat()}] Pipeline update triggered for agent: {agent}")
        print(f"User-Agent: {request.headers.get('user-agent', 'Unknown')}")
        result = run_pipeline(agent=agent)
        if result.get("error"):
            print(f"\u274c Pipeline error: {result['error']}")
            print(f"\u274c Pipeline error: {result['error']}")
            return {
                "status": "error",
                "message": result['error'],
                "authenticated": result.get("authenticated", False)
            }
        processed = result.get("processed", 0)
        total = result.get("total", 0)
        print(f"\u2705 Pipeline completed for {agent}: {processed}/{total} documents processed")
        print(f"\u2705 Pipeline completed for {agent}: {processed}/{total} documents processed")
        return {
            "status": "success",
            "message": f"Pipeline executed successfully for {agent}",
            "agent": agent,
            "processed": processed,
            "total": total,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"\u274c Pipeline exception: {str(e)}")
        print(f"\u274c Pipeline exception: {str(e)}")
        return {
            "status": "error",
            "message": f"Pipeline failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

