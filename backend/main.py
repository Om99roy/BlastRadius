import hashlib
import json
import pathlib
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent import investigate
from .db import run
from .tools import REGISTRY

app = FastAPI(title="BlastRadius")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CACHE = pathlib.Path("cache")
CACHE.mkdir(exist_ok=True)


def _cache_path(tenant: str, question: str) -> pathlib.Path:
    norm = " ".join(question.lower().split())
    return CACHE / (hashlib.sha1(f"{tenant}|{norm}".encode()).hexdigest() + ".json")


class Ask(BaseModel):
    tenant: str = "acme"
    question: str
    fresh: bool = False  # True = skip the cache and run the agent live


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/graph/{tenant}")
def graph(tenant: str):
    """Full knowledge graph (all node types) for the 3D canvas."""
    rows = run(tenant, """MATCH (n)
        RETURN labels(n)[0] AS type, coalesce(n.name, n.id) AS id,
               n.title AS title, n.text AS text, n.summary AS summary, n.severity AS severity""")
    nodes = [r for r in rows if r["type"] != "Episode" and r["id"]]
    ids = {n["id"] for n in nodes}
    erows = run(tenant, """MATCH (a)-[r]->(b)
        RETURN coalesce(a.name, a.id) AS source, coalesce(b.name, b.id) AS target, type(r) AS rel""")
    edges = [e for e in erows if e["source"] in ids and e["target"] in ids]
    return {"nodes": nodes, "edges": edges}


@app.post("/api/ask")
def ask(body: Ask):
    def stream():
        path = _cache_path(body.tenant, body.question)
        if path.exists() and not body.fresh:
            yield f"data: {json.dumps({'type': 'cached'})}\n\n"
            for ev in json.loads(path.read_text()):
                time.sleep(0.5 if ev["type"] == "tool_call" else 0.15)
                yield f"data: {json.dumps(ev, default=str)}\n\n"
            return
        events, ok = [], False
        try:
            for ev in investigate(body.tenant, body.question):
                events.append(ev)
                ok = ev["type"] == "final"
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        except Exception as e:
            ok = False
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        if ok:  # only cache complete, successful investigations
            path.write_text(json.dumps(events, default=str))
    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/tool/{name}")
def tool(name: str, tenant: str = "acme", service: str = "paymentservice"):
    fn = REGISTRY[name]
    if name in ("find_experts", "similar_incidents", "related_decisions"):
        impacted = [r["service"] for r in REGISTRY["blast_radius"](tenant, service)["data"]]
        return fn(tenant, services=[service] + impacted)
    return fn(tenant, service=service)


# MUST stay last: a mount at "/" catches every path not matched above
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")