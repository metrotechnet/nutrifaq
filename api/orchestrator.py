from api.graph_layer import find_nodes_matches,  set_graph,multi_hop

def merge_results(vector_entities, graph_entities):
    scores = {}

    # vector weight = 1
    for e in vector_entities:
        scores[e] = scores.get(e, 0) + 1

    # graph weight = 2 (plus fort)
    for e in graph_entities:
        scores[e] = scores.get(e, 0) + 2

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    return [r[0] for r in ranked]


def smart_query(project_name, collection_name, nodes, edges, query):

    # =========================
    # 🔥 LOAD GRAPH
    # =========================
    set_graph(project_name)

    # =========================
    # 🧠 DOMAIN DETECTION
    # =========================
    from api.utils import detect_domains
    vector_entities = query.get("domains", [])
    # convert domain to ids


    # =========================
    # 🔍 VECTOR SEARCH
    # =========================
    from api.query_chromadb import  query_vector_db, extract_entities

    vector_results = query_vector_db(project_name, collection_name, query)
    vector_entities += extract_entities(vector_results)
    
    # in all nodes of graphe compage domaine with 

    node_list = find_nodes_matches(vector_entities, nodes)


    # =========================
    # 🔗 GRAPH
    # =========================
    graph_entities = []


    if node_list:
        graph_entities = multi_hop(
            node_list,
            edges
        )


    return {
        "project": project_name,
        "query": query,
        "search_vector": vector_results,
        "graph_links": graph_entities
    }