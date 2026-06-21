"""Iterate Semantic Scholar bulk queries to land near ~3,500 papers."""
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("SEMANTIC_SCHOLAR_KEY", "")
if not key or key in ("", "leave_for_now", "your_s2_key_here"):
    raise SystemExit("SEMANTIC_SCHOLAR_KEY not set in .env")

headers = {"x-api-key": key}
URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
SLEEP = 2.5  # bulk endpoint throttles aggressively despite docs


def count_papers(query: str, year: str) -> int:
    params = {
        "query": query,
        "year": year,
        "fieldsOfStudy": "Computer Science",
        "fields": "paperId",
    }
    r = requests.get(URL, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json().get("total", 0)


if __name__ == "__main__":
    # Each row: (label, query, year_range)
    tests = [
        ("RAG exact 2022-26",
         '"retrieval augmented generation"', "2022-2026"),
        ("RAG exact 2023-26",
         '"retrieval augmented generation"', "2023-2026"),
        ("RAG + variants 2023-26",
         '"retrieval augmented generation" | "retrieval-augmented generation" | RAG', "2023-2026"),
        ("RAG + LLM context 2022-26",
         '("retrieval augmented" | RAG) + ("language model" | LLM)', "2022-2026"),
        ("RAG + LLM context 2023-26",
         '("retrieval augmented" | RAG) + ("language model" | LLM)', "2023-2026"),
        ("Dense + LLM 2022-26",
         '("dense retrieval" | "dense passage retrieval") + ("language model" | LLM)', "2022-2026"),
        ("RAG + dense + LLM 2022-26",
         '("retrieval augmented" | RAG | "dense passage retrieval" | "dense retrieval") + ("language model" | LLM)', "2022-2026"),
        ("RAG + KG + LLM 2022-26",
         '("retrieval augmented" | RAG) + ("knowledge graph" | "language model" | LLM)', "2022-2026"),
    ]

    print(f"{'Label':<32} {'Year':<10} {'Total':>10}")
    print("-" * 56)
    for label, query, year in tests:
        try:
            total = count_papers(query, year)
            print(f"{label:<32} {year:<10} {total:>10}")
        except Exception as e:
            print(f"{label:<32} {year:<10} ERROR: {str(e)[:30]}")
        time.sleep(SLEEP)