"""Ingest Author and Venue nodes + their edges to Papers."""
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
BATCH_SIZE = 200  # smaller because each paper's authors list expands inside Cypher

INGEST_AUTHORS = """
UNWIND $batch AS row
MATCH (p:Paper {paperId: row.paperId})
UNWIND row.authors AS author
WITH p, author
WHERE author.authorId IS NOT NULL
MERGE (a:Author {authorId: author.authorId})
SET a.name = coalesce(a.name, author.name)
MERGE (p)-[:AUTHORED_BY]->(a)
"""

INGEST_VENUES = """
UNWIND $batch AS row
MATCH (p:Paper {paperId: row.paperId})
WITH p, row
WHERE row.venue IS NOT NULL AND row.venue <> ''
MERGE (v:Venue {name: row.venue})
MERGE (p)-[:PUBLISHED_AT]->(v)
"""


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    total = 0
    n_papers_with_authors = 0
    n_papers_with_venue = 0
    n_total_author_slots = 0

    with driver.session() as session:
        batch = []
        for line in open(PAPERS_PATH, encoding="utf-8"):
            paper = json.loads(line)
            authors_raw = paper.get("authors") or []
            # Keep only authors with an authorId, and strip to minimal fields
            authors_clean = [
                {"authorId": a.get("authorId"), "name": a.get("name") or ""}
                for a in authors_raw
                if a.get("authorId")
            ]
            if authors_clean:
                n_papers_with_authors += 1
            n_total_author_slots += len(authors_clean)

            venue = paper.get("venue") or ""
            if venue:
                n_papers_with_venue += 1

            batch.append({
                "paperId": paper["paperId"],
                "authors": authors_clean,
                "venue": venue,
            })

            if len(batch) >= BATCH_SIZE:
                session.run(INGEST_AUTHORS, batch=batch)
                session.run(INGEST_VENUES, batch=batch)
                total += len(batch)
                print(f"  Processed {total} papers")
                batch = []

        if batch:
            session.run(INGEST_AUTHORS, batch=batch)
            session.run(INGEST_VENUES, batch=batch)
            total += len(batch)
            print(f"  Processed {total} papers")

        print()
        print(f"Papers with at least one Author: {n_papers_with_authors:,}")
        print(f"Total author slots:              {n_total_author_slots:,}")
        print(f"Papers with a venue:             {n_papers_with_venue:,}")

        # Verify
        n_authors = session.run("MATCH (a:Author) RETURN count(a) AS n").single()["n"]
        n_author_edges = session.run("MATCH ()-[r:AUTHORED_BY]->() RETURN count(r) AS n").single()["n"]
        n_venues = session.run("MATCH (v:Venue) RETURN count(v) AS n").single()["n"]
        n_venue_edges = session.run("MATCH ()-[r:PUBLISHED_AT]->() RETURN count(r) AS n").single()["n"]
        print(f"\nTotal Author nodes:      {n_authors:,}")
        print(f"Total AUTHORED_BY edges: {n_author_edges:,}")
        print(f"Total Venue nodes:       {n_venues:,}")
        print(f"Total PUBLISHED_AT edges:{n_venue_edges:,}")

        # Most prolific authors in the corpus
        print("\nTop 10 most-prolific authors in corpus:")
        result = session.run("""
            MATCH (a:Author)<-[:AUTHORED_BY]-(p:Paper)
            RETURN a.name AS name, count(p) AS papers
            ORDER BY papers DESC
            LIMIT 10
        """)
        for r in result:
            print(f"  {r['papers']:>3} papers  {r['name']}")

        # Top venues
        print("\nTop 10 venues by paper count:")
        result = session.run("""
            MATCH (v:Venue)<-[:PUBLISHED_AT]-(p:Paper)
            RETURN v.name AS name, count(p) AS papers
            ORDER BY papers DESC
            LIMIT 10
        """)
        for r in result:
            name = (r["name"] or "")[:70]
            print(f"  {r['papers']:>4}  {name}")

    driver.close()
    print("\nAuthor + Venue ingestion complete.")


if __name__ == "__main__":
    main()


