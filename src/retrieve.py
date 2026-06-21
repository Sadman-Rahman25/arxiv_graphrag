"""CLI wrapper for dual retrieval.
Usage:
  python src/retrieve.py "your query here"
  python src/retrieve.py "your query" --top-k 10
"""
import argparse, os, logging
logging.getLogger("neo4j").setLevel(logging.ERROR)
from neo4j import GraphDatabase
from dotenv import load_dotenv
from retrieve_dual import dual_search, format_results
from retrieve_vector import get_model

load_dotenv()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("query")
    p.add_argument("--top-k", type=int, default=10)
    args = p.parse_args()

    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD"))
    )
    get_model()
    results = dual_search(driver, args.query, top_k=args.top_k, verbose=True)
    format_results(args.query, results)
    driver.close()

if __name__ == "__main__":
    main()