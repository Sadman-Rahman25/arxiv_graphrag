"""Day 4 Gate 8 - Final validation of the GraphRAG knowledge graph.

Runs counts, constraint checks, orphan checks, connectivity sanity,
and a sample multi-hop traversal. Adjust property names (canonical,
name, etc.) to match your actual schema if different.
"""
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

URI  = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PWD  = os.getenv("NEO4J_PASSWORD")

EXPECTED_NODES = {
    "Paper":   3500,
    "Method":  157,
    "Dataset": 47,
    "Author":  16976,
    "Venue":   862,
}
EXPECTED_EDGES = {
    "AUTHORED_BY":  21082,
    "PUBLISHED_AT": 3417,
}

def section(title):
    print(f"\n{'=' * 64}\n{title}\n{'=' * 64}")

def run(session, cypher, **params):
    return list(session.run(cypher, **params))

driver = GraphDatabase.driver(URI, auth=(USER, PWD))

with driver.session() as s:
    # ---------- Node counts ----------
    section("Node counts")
    all_pass = True
    for label, expected in EXPECTED_NODES.items():
        actual = run(s, f"MATCH (n:{label}) RETURN count(n) AS c")[0]["c"]
        status = "OK" if actual == expected else "MISMATCH"
        if status != "OK":
            all_pass = False
        print(f"  {label:10s} {actual:>7,}  (expected {expected:,})  [{status}]")

    # ---------- Edge counts ----------
    section("Edge counts (all relationship types)")
    edge_rows = run(s, """
        MATCH ()-[r]->()
        RETURN type(r) AS rel_type, count(*) AS c
        ORDER BY c DESC
    """)
    for row in edge_rows:
        exp = EXPECTED_EDGES.get(row["rel_type"])
        marker = ""
        if exp is not None:
            marker = "  [OK]" if row["c"] == exp else f"  [MISMATCH expected {exp:,}]"
            if row["c"] != exp:
                all_pass = False
        print(f"  {row['rel_type']:28s} {row['c']:>8,}{marker}")

    # ---------- Constraints ----------
    section("Uniqueness constraints")
    for row in run(s, "SHOW CONSTRAINTS"):
        d = dict(row)
        print(f"  {d.get('name')}: {d.get('labelsOrTypes')} {d.get('properties')} [{d.get('type')}]")

    # ---------- Indexes (informational) ----------
    section("Indexes")
    for row in run(s, "SHOW INDEXES"):
        d = dict(row)
        if d.get("type") in ("RANGE", "TEXT", "FULLTEXT", "VECTOR"):
            print(f"  {d.get('name')}: {d.get('labelsOrTypes')} {d.get('properties')} [{d.get('type')}]")

    # ---------- Orphan checks ----------
    section("Orphan checks (lower is better, zero is ideal except where noted)")
    orphan_queries = [
        ("Papers w/ no author",          "MATCH (p:Paper) WHERE NOT (p)-[:AUTHORED_BY]->() RETURN count(p) AS c"),
        ("Papers w/ no venue",           "MATCH (p:Paper) WHERE NOT (p)-[:PUBLISHED_AT]->() RETURN count(p) AS c"),
        ("Papers w/ no method mention",  "MATCH (p:Paper) WHERE NOT (p)-[:MENTIONS_METHOD]->() RETURN count(p) AS c"),
        ("Papers w/ no CITES in or out", "MATCH (p:Paper) WHERE NOT (p)-[:CITES]-() RETURN count(p) AS c"),
        ("Methods with zero mentions",   "MATCH (m:Method) WHERE NOT ()-[:MENTIONS_METHOD]->(m) RETURN count(m) AS c"),
        ("Datasets with zero mentions",  "MATCH (d:Dataset) WHERE NOT ()-[:MENTIONS_DATASET]->(d) RETURN count(d) AS c"),
        ("Authors with zero papers",     "MATCH (a:Author) WHERE NOT (a)<-[:AUTHORED_BY]-() RETURN count(a) AS c"),
        ("Venues with zero papers",      "MATCH (v:Venue)  WHERE NOT (v)<-[:PUBLISHED_AT]-() RETURN count(v) AS c"),
    ]
    for label, q in orphan_queries:
        c = run(s, q)[0]["c"]
        print(f"  {label:38s} {c:>6,}")

    # ---------- Connectivity sanity ----------
    section("Paper-node connectivity")
    deg = run(s, """
        MATCH (p:Paper)
        OPTIONAL MATCH (p)-[r]-()
        WITH p, count(r) AS d
        RETURN avg(d) AS avg_deg, percentileCont(d, 0.5) AS median_deg,
               min(d) AS min_deg, max(d) AS max_deg
    """)[0]
    print(f"  avg degree:    {deg['avg_deg']:.1f}")
    print(f"  median degree: {deg['median_deg']:.0f}")
    print(f"  min / max:     {deg['min_deg']} / {deg['max_deg']}")

    cite_stats = run(s, """
        MATCH (p:Paper)
        OPTIONAL MATCH (p)-[r:CITES]->()
        WITH p, count(r) AS outdeg
        RETURN avg(outdeg) AS avg_out, max(outdeg) AS max_out
    """)[0]
    print(f"  avg CITES outdegree: {cite_stats['avg_out']:.1f}  (max {cite_stats['max_out']})")

    # ---------- Sample multi-hop traversal ----------
    section("Sample multi-hop: methods co-mentioned via citation")
    # NOTE: adjust Method property name if you used `name` or `id` instead of `canonical`
    sample = run(s, """
        MATCH (m:Method)<-[:MENTIONS_METHOD]-(p:Paper)
        WITH m, count(p) AS pop ORDER BY pop DESC LIMIT 1
        MATCH (m)<-[:MENTIONS_METHOD]-(p:Paper)-[:CITES]->(cited:Paper)-[:MENTIONS_METHOD]->(m2:Method)
        WHERE m2 <> m
        RETURN m.id AS seed_method,
               m2.id AS co_method,
               count(*) AS freq
        ORDER BY freq DESC LIMIT 10
    """)
    if sample:
        seed = sample[0]["seed_method"]
        print(f"  Seed method (most-mentioned): {seed}")
        for row in sample:
            print(f"    -> {row['co_method']:35s} freq={row['freq']:,}")
    else:
        print("  No results. Check Method.id property name in your schema.")

    # ---------- Top methods ----------
    section("Top 15 methods by mention count")
    for row in run(s, """
        MATCH (m:Method)<-[:MENTIONS_METHOD]-(p:Paper)
        RETURN m.id AS method, count(p) AS mentions
        ORDER BY mentions DESC LIMIT 15
    """):
        print(f"  {row['mentions']:>5,}  {row['method']}")

    # ---------- Top datasets ----------
    section("Top 10 datasets by mention count")
    for row in run(s, """
        MATCH (d:Dataset)<-[:MENTIONS_DATASET]-(p:Paper)
        RETURN d.id AS dataset, count(p) AS mentions
        ORDER BY mentions DESC LIMIT 10
    """):
        print(f"  {row['mentions']:>5,}  {row['dataset']}")

    # ---------- LLM extraction edges sanity ----------
    section("LLM extraction edge coverage")
    # Adjust relation types if you used different names (USES_METHOD, EVALUATES_ON, etc.)
    for rel in ["USES_METHOD", "INTRODUCES_METHOD", "EVALUATED_ON", "INTRODUCES_DATASET"]:
        c = run(s, f"MATCH ()-[r:{rel}]->() RETURN count(r) AS c")[0]["c"]
        if c > 0:
            print(f"  {rel:20s} {c:>6,}")

driver.close()
print("\n" + ("=" * 64))
print("VALIDATION COMPLETE" + ("  [ALL GATES GREEN]" if all_pass else "  [MISMATCHES — review above]"))
print("=" * 64)
