"""Ingest LLM extraction edges + scope flags from llm_extractions_full.jsonl.

Only creates edges where head/tail map to canonical Method/Dataset IDs.
Novel methods/datasets noted in extraction file but not added to graph
(preserves canonical-ID purity).
"""
import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()
URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")

EXTRACTIONS_PATH = Path("data/extractions/llm_extractions_full.jsonl")


def canonicalize(name: str) -> str:
    """Map a free-form name from LLM output to a likely canonical ID format."""
    if not name:
        return ""
    s = name.strip().lower()
    s = re.sub(r"[-\s]+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s


INGEST_INTRO_METHOD = """
UNWIND $batch AS row
MATCH (p:Paper {paperId: row.paperId})
MATCH (m:Method {id: row.entity_id})
MERGE (p)-[:INTRODUCES_METHOD]->(m)
"""

INGEST_INTRO_DATASET = """
UNWIND $batch AS row
MATCH (p:Paper {paperId: row.paperId})
MATCH (d:Dataset {id: row.entity_id})
MERGE (p)-[:INTRODUCES_DATASET]->(d)
"""

INGEST_USES = """
UNWIND $batch AS row
MATCH (p:Paper {paperId: row.paperId})
MATCH (m:Method {id: row.entity_id})
MERGE (p)-[:USES_METHOD]->(m)
"""

INGEST_EVAL_ON = """
UNWIND $batch AS row
MATCH (p:Paper {paperId: row.paperId})
MATCH (d:Dataset {id: row.entity_id})
MERGE (p)-[:EVALUATED_ON]->(d)
"""

UPDATE_SCOPE = """
UNWIND $batch AS row
MATCH (p:Paper {paperId: row.paperId})
SET p.llm_in_scope = row.in_scope,
    p.llm_scope_reason = row.scope_reason
"""


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    print("Loading valid canonical IDs from graph...")
    valid_methods = set()
    valid_datasets = set()
    with driver.session() as session:
        for r in session.run("MATCH (m:Method) RETURN m.id AS id"):
            valid_methods.add(r["id"])
        for r in session.run("MATCH (d:Dataset) RETURN d.id AS id"):
            valid_datasets.add(r["id"])
    print(f"  {len(valid_methods)} canonical methods, {len(valid_datasets)} canonical datasets")

    intro_method = []
    intro_dataset = []
    uses_method = []
    eval_on = []
    scope_updates = []

    n_records = 0
    n_relations_seen = 0
    n_relations_mapped = 0
    n_relations_skipped = 0

    for line in open(EXTRACTIONS_PATH, encoding="utf-8"):
        rec = json.loads(line)
        paper_id = rec["paperId"]
        n_records += 1

        scope_updates.append({
            "paperId": paper_id,
            "in_scope": rec.get("in_scope", True),
            "scope_reason": rec.get("scope_reason", "")[:200],
        })

        for rel in rec.get("relations", []):
            n_relations_seen += 1
            head = canonicalize(rel.get("head", ""))
            tail = canonicalize(rel.get("tail", "")) if rel.get("tail") else None
            rtype = (rel.get("type") or "").upper()

            mapped = False
            if rtype == "INTRODUCES":
                if head in valid_methods:
                    intro_method.append({"paperId": paper_id, "entity_id": head})
                    mapped = True
                elif head in valid_datasets:
                    intro_dataset.append({"paperId": paper_id, "entity_id": head})
                    mapped = True
            elif rtype == "USES":
                if head in valid_methods:
                    uses_method.append({"paperId": paper_id, "entity_id": head})
                    mapped = True
                if tail and tail in valid_methods:
                    uses_method.append({"paperId": paper_id, "entity_id": tail})
                    mapped = True
            elif rtype == "EVALUATED_ON":
                if tail and tail in valid_datasets:
                    eval_on.append({"paperId": paper_id, "entity_id": tail})
                    mapped = True
                elif head in valid_datasets:
                    eval_on.append({"paperId": paper_id, "entity_id": head})
                    mapped = True

            if mapped:
                n_relations_mapped += 1
            else:
                n_relations_skipped += 1

    print(f"\nProcessed {n_records} extractions")
    print(f"Relations seen:       {n_relations_seen}")
    print(f"Relations mapped:     {n_relations_mapped} (head/tail in canonical gazetteer)")
    print(f"Relations skipped:    {n_relations_skipped} (novel names not in gazetteer)")
    print(f"\nEdge candidates:")
    print(f"  INTRODUCES_METHOD:  {len(intro_method)}")
    print(f"  INTRODUCES_DATASET: {len(intro_dataset)}")
    print(f"  USES_METHOD:        {len(uses_method)}")
    print(f"  EVALUATED_ON:       {len(eval_on)}")

    print("\nIngesting...")
    with driver.session() as session:
        if scope_updates:
            session.run(UPDATE_SCOPE, batch=scope_updates)
            print(f"  scope updated on {len(scope_updates)} papers")
        if intro_method:
            session.run(INGEST_INTRO_METHOD, batch=intro_method)
            print(f"  {len(intro_method)} INTRODUCES_METHOD edges")
        if intro_dataset:
            session.run(INGEST_INTRO_DATASET, batch=intro_dataset)
            print(f"  {len(intro_dataset)} INTRODUCES_DATASET edges")
        if uses_method:
            session.run(INGEST_USES, batch=uses_method)
            print(f"  {len(uses_method)} USES_METHOD edges")
        if eval_on:
            session.run(INGEST_EVAL_ON, batch=eval_on)
            print(f"  {len(eval_on)} EVALUATED_ON edges")

        print("\n=== Final edge counts ===")
        for et in ["INTRODUCES_METHOD", "INTRODUCES_DATASET", "USES_METHOD", "EVALUATED_ON"]:
            n = session.run(f"MATCH ()-[r:{et}]->() RETURN count(r) AS n").single()["n"]
            print(f"  {et}: {n}")

        n_out = session.run(
            "MATCH (p:Paper) WHERE p.llm_in_scope = false RETURN count(p) AS n"
        ).single()["n"]
        n_in = session.run(
            "MATCH (p:Paper) WHERE p.llm_in_scope = true RETURN count(p) AS n"
        ).single()["n"]
        print(f"\nLLM scope judgments: in={n_in}, out={n_out} (of 74 LLM-extracted papers)")

        print("\nSample papers introducing methods (highest cites):")
        result = session.run("""
            MATCH (p:Paper)-[:INTRODUCES_METHOD]->(m:Method)
            RETURN p.title AS title, p.citationCount AS cites, m.display AS method
            ORDER BY cites DESC
            LIMIT 8
        """)
        for r in result:
            title = (r["title"] or "")[:55]
            print(f"  cites={r['cites']:>5} {title}")
            print(f"          INTRODUCES_METHOD -> {r['method']}")

    driver.close()
    print("\nLLM extraction edge ingestion complete.")


if __name__ == "__main__":
    main()

