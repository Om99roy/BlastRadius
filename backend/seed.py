"""Seed a synthetic company graph. Usage: python -m backend.seed --tenant acme"""
import argparse
import random
from .db import graph_for

# Dependency graph loosely modelled on Google's Online Boutique (public demo app) + extras.
# (dependent, dependency)
DEPS = [
    ("frontend", "checkoutservice"), ("frontend", "productcatalogservice"),
    ("frontend", "recommendationservice"), ("frontend", "adservice"),
    ("frontend", "cartservice"), ("frontend", "currencyservice"),
    ("frontend", "shippingservice"), ("checkoutservice", "cartservice"),
    ("checkoutservice", "productcatalogservice"), ("checkoutservice", "paymentservice"),
    ("checkoutservice", "shippingservice"), ("checkoutservice", "emailservice"),
    ("checkoutservice", "currencyservice"), ("recommendationservice", "productcatalogservice"),
    ("cartservice", "redis-cart"), ("paymentservice", "fraud-engine"),
    ("fraud-engine", "feature-store"), ("shippingservice", "carrier-gateway"),
    ("emailservice", "smtp-relay"), ("productcatalogservice", "catalog-db"),
    ("feature-store", "catalog-db"), ("adservice", "feature-store"),
]
PEOPLE = {
    "Asha": ["checkoutservice", "paymentservice"], "Ben": ["frontend", "adservice"],
    "Chen": ["cartservice", "redis-cart"], "Dara": ["fraud-engine", "feature-store"],
    "Eli": ["shippingservice", "carrier-gateway"], "Farah": ["catalog-db", "productcatalogservice"],
    "Gus": ["emailservice", "smtp-relay", "currencyservice", "recommendationservice"],
}
INCIDENTS = [
    ("INC-101", "Checkout 500s after payment timeout", "sev1", "paymentservice", "Asha",
     "Raised client timeout, added circuit breaker", "RB-payments-timeout"),
    ("INC-102", "Cart items vanishing", "sev2", "redis-cart", "Chen",
     "Redis eviction policy fixed", "RB-redis-eviction"),
    ("INC-103", "Fraud engine latency spike", "sev2", "feature-store", "Dara",
     "Rolled back feature-store schema change", "RB-rollback"),
    ("INC-104", "Catalog DB connection exhaustion", "sev1", "catalog-db", "Farah",
     "Pool size raised, slow query killed", "RB-db-pool"),
    ("INC-105", "Payment declines surge", "sev2", "fraud-engine", "Dara",
     "Model threshold reverted", "RB-rollback"),
    ("INC-106", "Shipping quotes failing", "sev3", "carrier-gateway", "Eli",
     "Rotated expired carrier API key", "RB-key-rotation"),
]
DECISIONS = [
    ("DEC-1", "Use circuit breakers on all payment calls", "paymentservice", "ADR-014"),
    ("DEC-2", "Freeze feature-store schema changes on Fridays", "feature-store", "ADR-021"),
    ("DEC-3", "catalog-db is single-writer until Q1", "catalog-db", "ADR-030"),
]


def seed(tenant: str):
    g = graph_for(tenant)
    try:
        g.query("MATCH (n) DETACH DELETE n")
    except Exception:
        pass
    for ddl in ["CREATE INDEX FOR (s:Service) ON (s.name)",
                "CREATE INDEX FOR (p:Person) ON (p.name)"]:
        try:
            g.query(ddl)
        except Exception:
            pass

    names = sorted({n for pair in DEPS for n in pair})
    g.query("UNWIND $names AS n MERGE (:Service {name:n})", {"names": names})
    g.query("""UNWIND $deps AS d
               MATCH (a:Service {name:d[0]}), (b:Service {name:d[1]})
               MERGE (a)-[:DEPENDS_ON]->(b)""", {"deps": [list(d) for d in DEPS]})

    for person, owned in PEOPLE.items():
        g.query("""MERGE (p:Person {name:$p})
                   WITH p UNWIND $owned AS s
                   MATCH (sv:Service {name:s}) MERGE (p)-[:OWNS]->(sv)""",
                {"p": person, "owned": owned})

    random.seed(7)
    for iid, title, sev, svc, fixer, summary, rb in INCIDENTS:
        g.query("""MATCH (s:Service {name:$svc}), (p:Person {name:$fixer})
                   CREATE (i:Incident {id:$id, title:$title, severity:$sev, summary:$summary})
                   MERGE (r:Runbook {name:$rb})
                   CREATE (i)-[:AFFECTED]->(s), (i)-[:RESOLVED_BY]->(p), (i)-[:FOLLOWED]->(r)""",
                {"svc": svc, "fixer": fixer, "id": iid, "title": title, "sev": sev,
                 "summary": summary, "rb": rb})

    for did, text, svc, doc in DECISIONS:
        g.query("""MATCH (s:Service {name:$svc})
                   CREATE (d:Decision {id:$id, text:$text})-[:ABOUT]->(s)
                   MERGE (x:Doc {name:$doc}) CREATE (d)-[:DOCUMENTED_IN]->(x)""",
                {"svc": svc, "id": did, "text": text, "doc": doc})
    print(f"Seeded tenant '{tenant}' with {len(names)} services.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="acme")
    seed(ap.parse_args().tenant)
