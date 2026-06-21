"""Ingest CITES edges from references in papers.jsonl.

Only creates edges where both papers are in the corpus (internal citation graph).
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()
URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")

PAPERS_PATH = Path("data/raw/papers.jsonl")
BATCH_SIZE = 1000

INGEST_CITES_CYPHER = """
UNWIND $batch AS row
MATCH (src:Paper {paperId: row.src})
MATCH (dst:Paper {paperId: row.dst})
MERGE (src)-[:CITES]->(dst)
"""


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    # Pass 1: load all corpus paperIds for filtering
    print("Loading corpus paperIds...")
    corpus_ids = set()
    for line in open(PAPERS_PATH, encoding="utf-8"):
        paper = json.loads(line)
        corpus_ids.add(paper["paperId"])
    print(f"Corpus size: {len(corpus_ids):,} papers")

    # Pass 2: extract internal citation edges
    print("\nExtracting citation edges (internal only)...")
    edges = []
    total_refs = 0
    n_papers_with_refs = 0

    for line in open(PAPERS_PATH, encoding="utf-8"):
        paper = json.loads(line)
        refs = paper.get("references") or []
        if refs:
            n_papers_with_refs += 1
        for ref in refs:
            if not ref:
                continue
            ref_id = ref.get("paperId")
            if not ref_id:
                continue
            total_refs += 1
            if ref_id in corpus_ids and ref_id != paper["paperId"]:  # skip self-citations
                edges.append({"src": paper["paperId"], "dst": ref_id})

    print(f"  Papers with at least one reference: {n_papers_with_refs:,}")
    print(f"  Total references in dataset:        {total_refs:,}")
    print(f"  Internal (both ends in corpus):     {len(edges):,}")
    if total_refs:
        print(f"  Internal-citation ratio:            {100*len(edges)/total_refs:.1f}%")

    # Pass 3: bulk ingest
    print(f"\nIngesting in batches of {BATCH_SIZE}...")
    with driver.session() as session:
        for i in range(0, len(edges), BATCH_SIZE):
            batch = edges[i:i + BATCH_SIZE]
            session.run(INGEST_CITES_CYPHER, batch=batch)
            print(f"  Ingested {min(i + BATCH_SIZE, len(edges)):,} / {len(edges):,} edges")

        # Verification
        print()
        cites_count = session.run("MATCH ()-[r:CITES]->() RETURN count(r) AS n").single()["n"]
        print(f"Total CITES edges in graph: {cites_count:,}")

        # Most-cited papers (highest in-degree)
        print("\nTop 10 most-cited papers (within the corpus):")
        result = session.run("""
            MATCH (p:Paper)<-[:CITES]-(citing:Paper)
            RETURN p.title AS title, p.year AS year, count(citing) AS cited_by
            ORDER BY cited_by DESC
            LIMIT 10
        """)
        for record in result:
            title = (record["title"] or "")[:65]
            print(f"  [{record['year']}] cited_by={record['cited_by']:>4} {title}")

        # Most-citing papers (highest out-degree)
        print("\nTop 5 most-citing papers (highest out-degree):")
        result = session.run("""
            MATCH (p:Paper)-[:CITES]->(cited:Paper)
            RETURN p.title AS title, p.year AS year, count(cited) AS cites_count
            ORDER BY cites_count DESC
            LIMIT 5
        """)
        for record in result:
            title = (record["title"] or "")[:65]
            print(f"  [{record['year']}] cites={record['cites_count']:>3} {title}")

        # Microsoft GraphRAG paper's citation neighborhood
        print("\nMicrosoft GraphRAG paper citation neighborhood:")
        result = session.run("""
            MATCH (p:Paper)
            WHERE p.title CONTAINS 'From Local to Global'
            OPTIONAL MATCH (p)-[:CITES]->(cited)
            OPTIONAL MATCH (citer)-[:CITES]->(p)
            RETURN p.title AS title,
                   count(DISTINCT cited) AS papers_it_cites,
                   count(DISTINCT citer) AS papers_citing_it
        """)
        for record in result:
            title = (record["title"] or "")[:65]
            print(f"  {title}")
            print(f"    cites internally:    {record['papers_it_cites']} other corpus papers")
            print(f"    cited internally by: {record['papers_citing_it']} other corpus papers")

    driver.close()
    print("\nCitation edge ingestion complete.")


if __name__ == "__main__":
    main()


