"""Iterate on Semantic Scholar query until we hit ~3,500 papers.

Uses /paper/search endpoint (works anonymously) to get total counts.
Bulk fetching on Day 2 will need the API key.
"""
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("SEMANTIC_SCHOLAR_KEY", "")
headers = {"x-api-key": key} if key and key not in ("", "leave_for_now", "your_s2_key_here") else {}

URL = "https://api.semanticscholar.org/graph/v1/paper/search"


def count_papers(query: str, year: str = "2020-2026") -> int:
    """Return total paper count for a query."""
    params = {
        "query": query,
        "year": year,
        "fieldsOfStudy": "Computer Science",
        "limit": 1,  # we only need the total, not the results
        "fields": "paperId",
    }
    r = requests.get(URL, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json().get("total", 0)


if __name__ == "__main__":
    queries_to_test = [
        "retrieval augmented generation",
        "retrieval augmented generation dense",
        "RAG retrieval augmented",
        "dense passage retrieval",
        "retrieval augmented generation knowledge graph",
        "GraphRAG knowledge graph retrieval",
        "retrieval augmented generation LLM",
        "RAG language model retrieval",
    ]

    print(f"{'Query':<55} {'Total':>10}")
    print("-" * 67)
    for q in queries_to_test:
        try:
            total = count_papers(q)
            print(f"{q[:53]:<55} {total:>10}")
            time.sleep(1.1)  # respect 1 req/sec anonymous rate limit
        except Exception as e:
            print(f"{q[:53]:<55} ERROR: {e}")
            time.sleep(1.1)