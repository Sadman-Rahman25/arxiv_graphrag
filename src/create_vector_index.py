"""Day 5 Gate 2 - Create Neo4j vector index on Paper.embedding.

After Gate 1, all 3,500 papers have a 768-dim embedding property.
This script creates the native vector index that makes nearest-neighbor
search fast (O(log n) HNSW instead of O(n) brute force).

Neo4j 5.x supports cosine, euclidean, and dot-product similarity.
We use cosine because BGE embeddings are L2-normalized (so cosine
equals dot product, but cosine is the canonical choice for embeddings).
"""
import os
import time
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

URI  = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PWD  = os.getenv("NEO4J_PASSWORD")

INDEX_NAME = "paper_embedding_idx"
DIMENSIONS = 768
SIMILARITY = "cosine"


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PWD))

    with driver.session() as s:
        # Check if index already exists
        existing = list(s.run("SHOW INDEXES WHERE name = $name", name=INDEX_NAME))
        if existing:
            d = dict(existing[0])
            print(f"Index '{INDEX_NAME}' already exists:")
            print(f"  state:        {d.get('state')}")
            print(f"  type:         {d.get('type')}")
            print(f"  labels:       {d.get('labelsOrTypes')}")
            print(f"  properties:   {d.get('properties')}")
            print(f"  populated:    {d.get('populationPercent')}%")
            print("\nSkipping creation. Drop it manually with DROP INDEX if you need to recreate.")
        else:
            print(f"Creating vector index '{INDEX_NAME}'...")
            print(f"  dimensions: {DIMENSIONS}")
            print(f"  similarity: {SIMILARITY}")

            s.run(f"""
                CREATE VECTOR INDEX {INDEX_NAME} IF NOT EXISTS
                FOR (p:Paper) ON (p.embedding)
                OPTIONS {{
                  indexConfig: {{
                    `vector.dimensions`: {DIMENSIONS},
                    `vector.similarity_function`: '{SIMILARITY}'
                  }}
                }}
            """)
            print("  Created.")

        # Wait for index to come ONLINE
        print("\nWaiting for index to populate...")
        for attempt in range(30):
            row = s.run("SHOW INDEXES WHERE name = $name", name=INDEX_NAME).single()
            if row is None:
                print(f"  attempt {attempt+1}: index not found yet")
                time.sleep(2)
                continue
            d = dict(row)
            state = d.get("state")
            pct   = d.get("populationPercent")
            print(f"  attempt {attempt+1}: state={state}  populated={pct}%")
            if state == "ONLINE":
                break
            time.sleep(2)
        else:
            print("  WARNING: index did not reach ONLINE within 60s. Check Neo4j logs.")

        # Final summary of all VECTOR indexes
        print("\nFinal VECTOR index inventory:")
        for row in s.run("SHOW INDEXES WHERE type = 'VECTOR'"):
            d = dict(row)
            print(f"  {d.get('name')}: {d.get('labelsOrTypes')} {d.get('properties')} "
                  f"[{d.get('state')}, {d.get('populationPercent')}%]")

    driver.close()
    print("\n[Gate 2 complete]  Next: retrieve_vector.py for first vector search.")


if __name__ == "__main__":
    main()