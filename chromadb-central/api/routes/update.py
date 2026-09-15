"""
Update API Routes

This module defines endpoints for reloading ChromaDB collections from GCS bucket.
"""
from fastapi import APIRouter, Request, Query
from datetime import datetime
import os

router = APIRouter()
from api.query_chromadb import (
    _download_chroma_db_from_bucket,
    _discover_projects_from_bucket,
    reload_project_collections,
    PROJECT_ROOT,
)


@router.post("/reload")
def reload_from_bucket(
    request: Request,
    project_name: str = Query(None, description="Project name to reload. If omitted, reloads all projects from bucket."),
):
    """
    Download chroma_db from GCS bucket and reload collections into memory.
    If project_name is provided, reloads only that project.
    If omitted, discovers all projects from the bucket and reloads them all.
    """
    try:
        kb_root = os.path.join(PROJECT_ROOT, "knowledge-base")

        if project_name:
            projects = [project_name]
        else:
            projects = _discover_projects_from_bucket()
            if not projects:
                return {"status": "error", "message": "No projects found in bucket."}

        results = {}
        for project in projects:
            try:
                _download_chroma_db_from_bucket(project, kb_root)
                reload_project_collections(project)
                results[project] = "ok"
            except Exception as e:
                results[project] = f"error: {str(e)}"

        return {
            "status": "success",
            "message": f"Reloaded {len(projects)} project(s) from bucket.",
            "projects": results,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        print(f"❌ Reload exception: {str(e)}")
        return {
            "status": "error",
            "message": f"Reload failed: {str(e)}",
            "timestamp": datetime.now().isoformat(),
        }

