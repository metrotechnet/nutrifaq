"""
Migration routes for monitoring and triggering PostgreSQL migration.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from api.migrate_to_postgres import (
    get_migration_status,
    list_chromadb_projects,
    migrate_all_projects,
    create_vector_table,
    migrate_collection_data
)

router = APIRouter(prefix="/migration", tags=["migration"])


@router.get("/status")
async def migration_status():
    """Get current migration status and statistics."""
    return get_migration_status()


@router.get("/projects")
async def available_projects():
    """List all available ChromaDB projects and collections."""
    projects = list_chromadb_projects()
    return {
        "projects": projects,
        "total_projects": len(projects),
        "total_collections": sum(len(cols) for cols in projects.values())
    }


@router.post("/migrate-all")
async def migrate_all(background_tasks: BackgroundTasks):
    """
    Trigger migration of all ChromaDB projects to PostgreSQL.
    Returns immediately; migration runs in background.
    """
    background_tasks.add_task(migrate_all_projects)
    return {
        "status": "migration_started",
        "message": "Migration is running in background. Check /migration/status for progress."
    }


@router.post("/migrate/{project_name}/{collection_name}")
async def migrate_single(project_name: str, collection_name: str, background_tasks: BackgroundTasks):
    """
    Trigger migration of a single collection.
    """
    # Validate project/collection exists in Chroma
    projects = list_chromadb_projects()
    if project_name not in projects or collection_name not in projects[project_name]:
        raise HTTPException(
            status_code=404,
            detail=f"Collection {collection_name} not found in project {project_name}"
        )
    
    # Create table
    table_created, msg = create_vector_table(project_name, collection_name)
    if not table_created:
        raise HTTPException(status_code=400, detail=msg)
    
    # Migrate data in background
    background_tasks.add_task(migrate_collection_data, project_name, collection_name)
    
    return {
        "status": "migration_started",
        "project": project_name,
        "collection": collection_name,
        "message": "Data migration is running in background."
    }


@router.get("/health")
async def migration_health():
    """Check if migration infrastructure is available."""
    status = get_migration_status()
    return {
        "postgres_connected": status.get("postgres_available", False),
        "available_tables": len(status.get("tables", [])),
        "total_documents": status.get("total_documents", 0)
    }
