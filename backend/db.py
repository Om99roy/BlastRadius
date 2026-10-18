import os
from dotenv import load_dotenv
from falkordb import FalkorDB

load_dotenv()

_db = None

def get_db() -> FalkorDB:
    global _db
    if _db is None:
        _db = FalkorDB(
            host=os.environ["FALKORDB_HOST"],
            port=int(os.environ["FALKORDB_PORT"]),
            username=os.getenv("FALKORDB_USERNAME") or None,
            password=os.getenv("FALKORDB_PASSWORD") or None,
            ssl=os.getenv("FALKORDB_SSL", "true").lower() == "true",
            socket_connect_timeout=10,
            socket_timeout=15
        )
    return _db

def graph_for(tenant: str):
    """One isolated graph per tenant (FalkorDB multigraph)."""
    return get_db().select_graph(f"blastradius_{tenant}")


def run(tenant: str, cypher: str, params: dict | None = None):
    """Execute Cypher and return query results as dictionaries."""
    res = graph_for(tenant).query(cypher, params or {})

    cols = [
        h[1] if isinstance(h, (list, tuple)) else h
        for h in res.header
    ]

    rows = [
        dict(zip(cols, row))
        for row in res.result_set
    ]

    return rows


