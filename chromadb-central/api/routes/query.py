
"""
Query Routes - Main query endpoint for streaming responses
"""
from fastapi import Body
from api.orchestrator import smart_query
from api.graph_layer import preload_graphs
from api.query_chromadb import list_collections, query_vector_db, preload_all_collections

from fastapi import APIRouter
from fastapi.responses import  JSONResponse


router = APIRouter()

@router.post("/query")
async def generic_query_post(
    payload: dict = Body(...)
):
    """
    Expects JSON body with:
      - project_name: str
      - collection_name: str (optional)
      - query: dict (requête ChromaDB)
    """
    print (f"Received query for project '{payload.get('project_name')}' collection '{payload.get('collection_name')}' ", flush=True)
    project_name = payload.get("project_name")
    collection_name = payload.get("collection_name")
    data = payload.get("query")

    result = query_vector_db(project_name, collection_name, data)
    # print(f"Query result: {result}", flush=True)
    return JSONResponse(content=result)

@router.post("/smart_query")
async def smart_query_post(
    payload: dict = Body(...)
):
    """
    Endpoint intelligent combinant:
    - vector search (Chroma)
    - graph reasoning
    - fusion des résultats

    Input:
    {
        "project_name": "innovia",
        "collection_name": "cctt",
        "query": "chimie verte bois"
    }
    """

    print(f"[SMART QUERY] Project='{payload.get('project_name')}' Collection='{payload.get('collection_name')}'", flush=True)

    project_name = payload.get("project_name")
    collection_name = payload.get("collection_name")
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    query = payload.get("query")

    # =========================
    # 🔍 GET COLLECTION
    # =========================
    # collection = get_collection(project_name, collection_name)

    # if collection is None:
    #     return JSONResponse(content={
    #         "error": f"Collection '{collection_name}' not found for project '{project_name}'"
    #     })

    try:
        # =========================
        # 🧠 SMART QUERY
        # =========================
        result = smart_query(project_name, collection_name, nodes, edges, query)

        return JSONResponse(content=result)

    except Exception as e:
        return JSONResponse(content={
            "error": "Smart query failed",
            "details": str(e)
        })
    
@router.get("/graph")
def get_graph():
    from api.graph_layer import load_graph
    return load_graph()
