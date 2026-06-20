"""Verify Python can talk to Neo4j."""
import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
)

with driver.session() as session:
    result = session.run("RETURN 'connection works' AS msg")
    print(result.single()["msg"])

driver.close()
print("Neo4j Python driver connected successfully.")