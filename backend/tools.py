"""Graph tools the agent can call. Each returns data + the Cypher used + a path for UI highlighting."""
import time
from .db import run

Q_BLAST = """
MATCH p = (d:Service)-[:DEPENDS_ON*1..4]->(s:Service {name:$name})
RETURN d.name AS service, length(p) AS hops, [n IN nodes(p) | n.name] AS path
ORDER BY hops
"""
Q_EXPERTS = """
MATCH (p:Person)<-[:RESOLVED_BY]-(i:Incident)-[:AFFECTED]->(s:Service)
WHERE s.name IN $services
RETURN p.name AS person, count(i) AS fixes
ORDER BY fixes DESC LIMIT 5
"""
Q_OWNERS = """
MATCH (p:Person)-[:OWNS]->(s:Service)
WHERE s.name IN $services
RETURN s.name AS service, p.name AS owner
"""
Q_INCIDENTS = """
MATCH (i:Incident)-[:AFFECTED]->(s:Service)
WHERE s.name IN $services
OPTIONAL MATCH (i)-[:FOLLOWED]->(r:Runbook)
OPTIONAL MATCH (i)-[:RESOLVED_BY]->(p:Person)
RETURN i.id AS id, i.title AS title, i.severity AS severity, i.summary AS fix,
       s.name AS service, r.name AS runbook
"""
Q_DECISIONS = """
MATCH (d:Decision)-[:ABOUT]->(s:Service) WHERE s.name IN $services
OPTIONAL MATCH (d)-[:DOCUMENTED_IN]->(x:Doc)
RETURN d.id AS id, d.text AS decision, s.name AS service, x.name AS source
"""
Q_RANK = """
CALL algo.pageRank('Service','DEPENDS_ON') YIELD node, score
RETURN node.name AS service, score ORDER BY score DESC LIMIT $k
"""
Q_RECALL = """
MATCH (e:Episode)-[:ABOUT]->(s:Service {name:$service})
RETURN e.question AS question, e.conclusion AS conclusion, e.ts AS ts
ORDER BY e.ts DESC LIMIT 5
"""
Q_REMEMBER = """
MATCH (s:Service {name:$service})
CREATE (e:Episode {question:$question, conclusion:$conclusion, ts:$ts})-[:ABOUT]->(s)
"""


def blast_radius(tenant, service, **_):
    rows = run(tenant, Q_BLAST, {"name": service})
    best = {}
    for r in rows:  # keep shortest path per impacted service
        if r["service"] not in best:
            best[r["service"]] = r
    return {"data": list(best.values()), "cypher": Q_BLAST.strip(),
            "path": sorted({n for r in best.values() for n in r["path"]})}


def find_experts(tenant, services, **_):
    return {"data": {"experts": run(tenant, Q_EXPERTS, {"services": services}),
                     "owners": run(tenant, Q_OWNERS, {"services": services})},
            "cypher": (Q_EXPERTS + Q_OWNERS).strip(), "path": services}


def similar_incidents(tenant, services, **_):
    return {"data": run(tenant, Q_INCIDENTS, {"services": services}),
            "cypher": Q_INCIDENTS.strip(), "path": services}


def related_decisions(tenant, services, **_):
    return {"data": run(tenant, Q_DECISIONS, {"services": services}),
            "cypher": Q_DECISIONS.strip(), "path": services}


def criticality(tenant, k=5, **_):
    rows = run(tenant, Q_RANK, {"k": k})
    return {"data": rows, "cypher": Q_RANK.strip(), "path": [r["service"] for r in rows]}


def recall(tenant, service, **_):
    return {"data": run(tenant, Q_RECALL, {"service": service}),
            "cypher": Q_RECALL.strip(), "path": [service]}


def remember(tenant, service, question, conclusion, **_):
    run(tenant, Q_REMEMBER, {"service": service, "question": question,
                             "conclusion": conclusion, "ts": int(time.time())})
    return {"data": "stored", "cypher": Q_REMEMBER.strip(), "path": [service]}


def _spec(name, desc, props, required):
    return {"name": name, "description": desc,
            "input_schema": {"type": "object", "properties": props, "required": required}}


_svc = {"type": "string", "description": "Exact service name, e.g. paymentservice"}
_svcs = {"type": "array", "items": {"type": "string"}, "description": "Service names"}

TOOL_SPECS = [
    _spec("recall", "Look up what we concluded in past sessions about a service. Call FIRST.",
          {"service": _svc}, ["service"]),
    _spec("blast_radius", "Transitive upstream services impacted if this service fails.",
          {"service": _svc}, ["service"]),
    _spec("find_experts", "Owners and people who resolved past incidents on these services.",
          {"services": _svcs}, ["services"]),
    _spec("similar_incidents", "Past incidents on these services with fixes and runbooks.",
          {"services": _svcs}, ["services"]),
    _spec("related_decisions", "Architecture decisions (ADRs) about these services.",
          {"services": _svcs}, ["services"]),
    _spec("criticality", "PageRank of services by how much others depend on them.",
          {"k": {"type": "integer"}}, []),
    _spec("remember", "Store the conclusion of this investigation for future sessions. Call LAST.",
          {"service": _svc, "question": {"type": "string"}, "conclusion": {"type": "string"}},
          ["service", "question", "conclusion"]),
]
REGISTRY = {f.__name__: f for f in
            [blast_radius, find_experts, similar_incidents, related_decisions,
             criticality, recall, remember]}
