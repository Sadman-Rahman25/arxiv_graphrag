"""Ingest Paper nodes into Neo4j from papers.jsonl.

Uses MERGE for idempotency and UNWIND for batching.
Safe to re-run — wont create duplicates because of paper_id_unique constraint.
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
BATCH_SIZE = 500

INGEST_CYPHER = """
UNWIND $batch AS row
MERGE (p:Paper {paperId: row.paperId})
SET p.title = row.title,
    p.abstract = row.abstract,
    p.year = row.year,
    p.citationCount = row.citationCount,
    p.influentialCitationCount = row.influentialCitationCount,
    p.arxivId = row.arxivId,
    p.venue = row.venue,
    p.fieldsOfStudy = row.fieldsOfStudy,
    p.publicationDate = row.publicationDate
"""


def to_record(paper: dict) -> dict:
    """Flatten the paper dict into a single-level record for Neo4j properties.

    Neo4j properties cant be nested dicts, so we extract arxivId from
    externalIds.ArXiv at ingestion time.
    """
    external_ids = paper.get("externalIds") or {}
    return {
        "paperId": paper["paperId"],
        "title": paper.get("title") or "",
        "abstract": paper.get("abstract") or "",
        "year": paper.get("year"),
        "citationCount": paper.get("citationCount") or 0,
        "influentialCitationCount": paper.get("influentialCitationCount") or 0,
        "arxivId": external_ids.get("ArXiv"),
        "venue": paper.get("venue") or "",
        "fieldsOfStudy": paper.get("fieldsOfStudy") or [],
        "publicationDate": paper.get("publicationDate"),
    }


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    total = 0

    with driver.session() as session:
        batch = []
        for line in open(PAPERS_PATH, encoding="utf-8"):
            paper = json.loads(line)
            batch.append(to_record(paper))

            if len(batch) >= BATCH_SIZE:
                session.run(INGEST_CYPHER, batch=batch)
                total += len(batch)
                print(f"  Ingested {total} papers")
                batch = []

        # Final partial batch
        if batch:
            session.run(INGEST_CYPHER, batch=batch)
            total += len(batch)
            print(f"  Ingested {total} papers")

        # Verify count
        print()
        result = session.run("MATCH (p:Paper) RETURN count(p) AS n")
        count = result.single()["n"]
        print(f"Total Paper nodes in graph: {count}")

        # Sample by citation count
        print("\nTop 5 papers by citation count:")
        result = session.run("""
            MATCH (p:Paper)
            RETURN p.title AS title, p.year AS year, p.citationCount AS cites
            ORDER BY cites DESC
            LIMIT 5
        """)
        for record in result:
            title = (record["title"] or "")[:65]
            print(f"  [{record['year']}] cites={record['cites']:>5} {title}")

        # Year distribution
        print("\nPaper count by year:")
        result = session.run("""
            MATCH (p:Paper)
            RETURN p.year AS year, count(p) AS n
            ORDER BY year
        """)
        for record in result:
            print(f"  {record['year']}: {record['n']:,}")

    driver.close()
    print("\nPaper ingestion complete.")


if __name__ == "__main__":
    main()


