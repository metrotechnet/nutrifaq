import json
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Cache des graphes chargés
_GRAPH_CACHE = {}

# Graph actif
_CURRENT_GRAPH = None


def set_graph(project_name):
    """
    Charge le graph correspondant au projet
    """
    global _CURRENT_GRAPH

    if project_name in _GRAPH_CACHE:
        _CURRENT_GRAPH = _GRAPH_CACHE[project_name]
        return _CURRENT_GRAPH

    graph_path = os.path.join(
        PROJECT_ROOT,
        "knowledge-base",
        project_name,
        "graph.json"
    )

    if not os.path.exists(graph_path):
        raise FileNotFoundError(f"Graph file not found for project '{project_name}'")

    with open(graph_path, encoding="utf-8") as f:
        graph = json.load(f)

    _GRAPH_CACHE[project_name] = graph
    _CURRENT_GRAPH = graph

    print(f"[Graph] Loaded graph for project '{project_name}'", flush=True)

    return graph


def get_graph():
    if _CURRENT_GRAPH is None:
        raise ValueError("Graph not set. Call set_graph(project_name) first.")
    return _CURRENT_GRAPH

def preload_graphs(projects):
    for p in projects:
        try:
            set_graph(p)
        except Exception as e:
            print(f"[Graph preload] Failed for {p}: {e}")

import unicodedata

def normalize(text):

    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    ).lower()

def find_nodes_matches(names,nodes_search=None):
    """
    graph: dict loaded from graph.json
    names: list of strings to match (e.g. ['sciences pures', 'nature et sante'])
    Returns: list of node ids with partial match in label
    """
    graph = get_graph()

    
    matches = []
    for node in graph.get('nodes', []):
        if not nodes_search or node.get('type') in nodes_search:
            label = node.get('label', '')
            norm_label = normalize(label)
            for query in names:
                norm_query = normalize(query)
                if norm_query in norm_label:
                    matches.append(node['id'])
    return matches

def find_neighbors(node_ids, edge_type=None):
    graph = get_graph()
    results = []

    for edge in graph["edges"]:
        if edge["source"] in node_ids:
            if edge_type is None or edge["type"] == edge_type:
                results.append(edge["target"])

    return list(set(results))


def multi_hop(start_nodes, path):
    current = []
    for edge_type in path:
        current += find_neighbors(start_nodes, edge_type)

    return list(set(current))

