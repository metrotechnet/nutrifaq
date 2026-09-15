def detect_domains(query):
    mapping = {
        "chimie": "domain_chimie",
        "bois": "domain_foresterie",
        "ia": "domain_ia",
        "santé": "domain_sante"
    }

    detected = []

    q = query.lower()
    for k, v in mapping.items():
        if k in q:
            detected.append(v)

    return detected