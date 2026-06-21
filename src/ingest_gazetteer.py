"""Ingest Method and Dataset nodes from gazetteer YAML files."""
import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")

METHODS_PATH = Path("gazetteer/methods.yaml")
DATASETS_PATH = Path("gazetteer/datasets.yaml")

INGEST_METHOD_CYPHER = """
UNWIND $batch AS row
MERGE (m:Method {id: row.id})
SET m.display = row.display,
    m.category = row.category,
    m.aliases = row.aliases
"""

INGEST_DATASET_CYPHER = """
UNWIND $batch AS row
MERGE (d:Dataset {id: row.id})
SET d.display = row.display,
    d.category = row.category,
    d.aliases = row.aliases
"""


def yaml_to_records(yaml_data: dict) -> list:
    """Convert {id: {display, aliases, category}} to [{id, display, ...}]."""
    return [
        {
            "id": canonical_id,
            "display": info.get("display", canonical_id),
            "category": info.get("category", "unknown"),
            "aliases": info.get("aliases", []),
        }
        for canonical_id, info in yaml_data.items()
    ]


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    with open(METHODS_PATH, encoding="utf-8") as f:
        methods = yaml.safe_load(f)
    with open(DATASETS_PATH, encoding="utf-8") as f:
        datasets = yaml.safe_load(f)

    method_records = yaml_to_records(methods)
    dataset_records = yaml_to_records(datasets)

    print(f"Loaded {len(method_records)} methods, {len(dataset_records)} datasets from YAML")

    with driver.session() as session:
        session.run(INGEST_METHOD_CYPHER, batch=method_records)
        print(f"Ingested {len(method_records)} Method nodes")

        session.run(INGEST_DATASET_CYPHER, batch=dataset_records)
        print(f"Ingested {len(dataset_records)} Dataset nodes")

        # Verify counts
        print()
        m_count = session.run("MATCH (m:Method) RETURN count(m) AS n").single()["n"]
        d_count = session.run("MATCH (d:Dataset) RETURN count(d) AS n").single()["n"]
        print(f"Total Method nodes:  {m_count}")
        print(f"Total Dataset nodes: {d_count}")

        # Method category distribution
        print("\nMethods by category (top 10):")
        result = session.run("""
            MATCH (m:Method)
            RETURN m.category AS cat, count(m) AS n
            ORDER BY n DESC
            LIMIT 10
        """)
        for record in result:
            print(f"  {record['cat']:<25} {record['n']:>3}")

        # Dataset category distribution
        print("\nDatasets by category:")
        result = session.run("""
            MATCH (d:Dataset)
            RETURN d.category AS cat, count(d) AS n
            ORDER BY n DESC
        """)
        for record in result:
            print(f"  {record['cat']:<25} {record['n']:>3}")

        # Sample lookups
        print("\nSample Method lookup (canonical 'rag'):")
        result = session.run("""
            MATCH (m:Method {id: 'rag'})
            RETURN m.display AS display, m.category AS cat, m.aliases AS aliases
        """)
        for record in result:
            print(f"  display={record['display']}, category={record['cat']}")
            print(f"  aliases={record['aliases']}")

    driver.close()
    print("\nGazetteer ingestion complete.")


if __name__ == "__main__":
    main()
