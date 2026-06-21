"""Ingest MENTIONS_METHOD and MENTIONS_DATASET edges from gazetteer_matches.jsonl."""
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()
URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")

MATCHES_PATH = Path("data/extractions/gazetteer_matches.jsonl")
BATCH_SIZE = 500

INGEST_METHOD_EDGES = """
UNWIND $batch AS row
MATCH (p:Paper {paperId: row.paperId})
UNWIND row.methods AS method_id
MATCH (m:Method {id: method_id})
MERGE (p)-[:MENTIONS_METHOD]->(m)
"""

INGEST_DATASET_EDGES = """
UNWIND $batch AS row
MATCH (p:Paper {paperId: row.paperId})
UNWIND row.datasets AS dataset_id
MATCH (d:Dataset {id: dataset_id})
MERGE (p)-[:MENTIONS_DATASET]->(d)
"""


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    total = 0

    with driver.session() as session:
        batch = []
        for line in open(MATCHES_PATH, encoding="utf-8"):
            rec = json.loads(line)
            # Only include records that have something to ingest
            if rec.get("methods") or rec.get("datasets"):
                batch.append({
                    "paperId": rec["paperId"],
                    "methods": rec.get("methods", []),
                    "datasets": rec.get("datasets", []),
                })

            if len(batch) >= BATCH_SIZE:
                session.run(INGEST_METHOD_EDGES, batch=batch)
                session.run(INGEST_DATASET_EDGES, batch=batch)
                total += len(batch)
                print(f"  Processed {total} papers")
                batch = []

        if batch:
            session.run(INGEST_METHOD_EDGES, batch=batch)
            session.run(INGEST_DATASET_EDGES, batch=batch)
            total += len(batch)
            print(f"  Processed {total} papers")

        # Verify edge counts
        print()
        m_count = session.run("MATCH ()-[r:MENTIONS_METHOD]->() RETURN count(r) AS n").single()["n"]
        d_count = session.run("MATCH ()-[r:MENTIONS_DATASET]->() RETURN count(r) AS n").single()["n"]
        print(f"Total MENTIONS_METHOD edges:  {m_count:,}")
        print(f"Total MENTIONS_DATASET edges: {d_count:,}")

        # Top 10 most-mentioned methods
        print("\nTop 10 most-mentioned methods:")
        result = session.run("""
            MATCH (m:Method)<-[:MENTIONS_METHOD]-(p:Paper)
            RETURN m.id AS id, m.display AS display, count(p) AS papers
            ORDER BY papers DESC
            LIMIT 10
        """)
        for record in result:
            print(f"  {record['id']:<25} {record['papers']:>5}  ({record['display']})")

        # Top 10 most-mentioned datasets
        print("\nTop 10 most-mentioned datasets:")
        result = session.run("""
            MATCH (d:Dataset)<-[:MENTIONS_DATASET]-(p:Paper)
            RETURN d.id AS id, d.display AS display, count(p) AS papers
            ORDER BY papers DESC
            LIMIT 10
        """)
        for record in result:
            print(f"  {record['id']:<25} {record['papers']:>5}  ({record['display']})")

        # Specific check: Microsoft GraphRAG paper and its methods
        print("\nMethods mentioned by the Microsoft GraphRAG paper:")
        result = session.run("""
            MATCH (p:Paper)-[:MENTIONS_METHOD]->(m:Method)
            WHERE p.title CONTAINS 'From Local to Global'
            RETURN m.id AS id, m.display AS display
            ORDER BY id
        """)
        rows = list(result)
        if rows:
            for r in rows:
                print(f"  {r['id']:<25} ({r['display']})")
        else:
            print("  (No matches found - check paper title)")

    driver.close()
    print("\nGazetteer edge ingestion complete.")


if __name__ == "__main__":
    main()


