"""Apply Neo4j schema: uniqueness constraints + indexes.

Idempotent — safe to re-run. Uses IF NOT EXISTS so existing constraints
are left alone.
"""
import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USER")
PASSWORD = os.getenv("NEO4J_PASSWORD")

CONSTRAINTS = [
    ("paper_id_unique",
     "CREATE CONSTRAINT paper_id_unique IF NOT EXISTS "
     "FOR (p:Paper) REQUIRE p.paperId IS UNIQUE"),
    ("method_id_unique",
     "CREATE CONSTRAINT method_id_unique IF NOT EXISTS "
     "FOR (m:Method) REQUIRE m.id IS UNIQUE"),
    ("dataset_id_unique",
     "CREATE CONSTRAINT dataset_id_unique IF NOT EXISTS "
     "FOR (d:Dataset) REQUIRE d.id IS UNIQUE"),
    ("author_id_unique",
     "CREATE CONSTRAINT author_id_unique IF NOT EXISTS "
     "FOR (a:Author) REQUIRE a.authorId IS UNIQUE"),
    ("venue_name_unique",
     "CREATE CONSTRAINT venue_name_unique IF NOT EXISTS "
     "FOR (v:Venue) REQUIRE v.name IS UNIQUE"),
]

# Additional indexes for properties we will query but that arent unique
INDEXES = [
    ("paper_year_idx",
     "CREATE INDEX paper_year_idx IF NOT EXISTS "
     "FOR (p:Paper) ON (p.year)"),
    ("paper_cites_idx",
     "CREATE INDEX paper_cites_idx IF NOT EXISTS "
     "FOR (p:Paper) ON (p.citationCount)"),
    ("method_category_idx",
     "CREATE INDEX method_category_idx IF NOT EXISTS "
     "FOR (m:Method) ON (m.category)"),
    ("dataset_category_idx",
     "CREATE INDEX dataset_category_idx IF NOT EXISTS "
     "FOR (d:Dataset) ON (d.category)"),
]


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    with driver.session() as session:
        print("Applying constraints...")
        for name, cypher in CONSTRAINTS:
            session.run(cypher)
            print(f"  OK {name}")

        print("\nApplying indexes...")
        for name, cypher in INDEXES:
            session.run(cypher)
            print(f"  OK {name}")

        print("\nVerifying constraints:")
        result = session.run("SHOW CONSTRAINTS YIELD name, labelsOrTypes, properties")
        for record in result:
            labels = record["labelsOrTypes"]
            props = record["properties"]
            print(f"  {record['name']:<30} on {labels}.{props}")

        print("\nVerifying indexes:")
        result = session.run("SHOW INDEXES YIELD name, labelsOrTypes, properties, type")
        for record in result:
            labels = record["labelsOrTypes"] or []
            props = record["properties"] or []
            idx_type = record["type"]
            print(f"  {record['name']:<30} ({idx_type}) on {labels}.{props}")

    driver.close()
    print("\nSchema setup complete.")


if __name__ == "__main__":
    main()


