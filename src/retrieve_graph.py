"""Day 5 Gate 4 - Graph-only retrieval via method/dataset bridge.

Per Day 4 finding (method-bridge dominates citation-bridge for multi-hop retrieval
in this corpus), this retriever:

1. Extracts methods + datasets mentioned in the query using gazetteer matching
   (same word-boundary + case-sensitive-for-acronyms logic as Day 3).
2. Finds papers that MENTIONS_METHOD or MENTIONS_DATASET those entities.
3. Scores by number of distinct bridges, with methods weighted 2x datasets.
4. Tiebreaks by citation count.

This is intentionally COMPLEMENTARY to vector retrieval, not a replacement:
- Vector wins when the query is descriptive but doesn't name specific methods
  (e.g., "long-context retrieval for legal documents" - no methods named).
- Graph wins when the query names specific methods/datasets that vector
  embedding doesn't strongly latch onto, or when method co-occurrence
  carries the semantic signal (e.g., "self-correcting RAG" should pull
  self_rag, CRAG, evidence-aware methods).

Gate 5 will fuse the two with RRF.
"""
import os
import re
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

URI  = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PWD  = os.getenv("NEO4J_PASSWORD")

# Method weight relative to dataset weight in bridge scoring
METHOD_WEIGHT  = 2
DATASET_WEIGHT = 1


def check_term(term, query_text):
    """Word-boundary match against query text.

    Short uppercase acronyms (<=5 chars with uppercase) require case-sensitive
    match to avoid e.g. matching 'rag' in 'fragment'. Phrases use
    case-insensitive matching. Same logic as Day 3 gazetteer matcher.
    """
    if not term:
        return False
    is_acronym = len(term) <= 5 and any(c.isupper() for c in term)
    if is_acronym:
        return bool(re.search(r'\b' + re.escape(term) + r'\b', query_text))
    return bool(re.search(r'\b' + re.escape(term.lower()) + r'\b', query_text.lower()))


def extract_entities_from_query(driver, query):
    """Match methods + datasets in the query against gazetteer entries in Neo4j.

    Returns (matched_methods, matched_datasets) where each is a dict
    {id -> matched_alias} so we can show what we matched on.
    """
    with driver.session() as s:
        methods = [dict(r) for r in s.run(
            "MATCH (m:Method)  RETURN m.id AS id, m.aliases AS aliases, m.display AS display"
        )]
        datasets = [dict(r) for r in s.run(
            "MATCH (d:Dataset) RETURN d.id AS id, d.aliases AS aliases, d.display AS display"
        )]

    matched_methods, matched_datasets = {}, {}

    for m in methods:
        terms = [m.get("display")] + (m.get("aliases") or [])
        for term in terms:
            if check_term(term, query):
                matched_methods[m["id"]] = term
                break

    for d in datasets:
        terms = [d.get("display")] + (d.get("aliases") or [])
        for term in terms:
            if check_term(term, query):
                matched_datasets[d["id"]] = term
                break

    return matched_methods, matched_datasets


def graph_search(driver, query, top_k=10, verbose=True):
    """Method-bridge graph retrieval.

    Returns list of dicts: {paperId, title, year, citationCount,
                            method_hits, dataset_hits, bridge_score,
                            matched_methods (per-paper)}.
    Empty list if query doesn't match any gazetteer entries.
    """
    methods, datasets = extract_entities_from_query(driver, query)

    if verbose:
        print(f"  Matched methods  ({len(methods)}): {sorted(methods.keys())}")
        print(f"  Matched datasets ({len(datasets)}): {sorted(datasets.keys())}")

    if not methods and not datasets:
        if verbose:
            print("  No gazetteer matches in query - graph retrieval returns empty.")
        return []

    with driver.session() as s:
        result = s.run(f"""
            MATCH (p:Paper)
            OPTIONAL MATCH (p)-[:MENTIONS_METHOD]->(m:Method)
              WHERE m.id IN $method_ids
            OPTIONAL MATCH (p)-[:MENTIONS_DATASET]->(d:Dataset)
              WHERE d.id IN $dataset_ids
            WITH p,
                 collect(DISTINCT m.id) AS hit_methods,
                 collect(DISTINCT d.id) AS hit_datasets
            WITH p, hit_methods, hit_datasets,
                 size(hit_methods)  AS method_hits,
                 size(hit_datasets) AS dataset_hits
            WHERE method_hits > 0 OR dataset_hits > 0
            WITH p, hit_methods, hit_datasets, method_hits, dataset_hits,
                 (method_hits * {METHOD_WEIGHT} + dataset_hits * {DATASET_WEIGHT}) AS bridge_score
            RETURN p.paperId       AS paperId,
                   p.title         AS title,
                   p.year          AS year,
                   p.citationCount AS citationCount,
                   hit_methods,
                   hit_datasets,
                   method_hits,
                   dataset_hits,
                   bridge_score
            ORDER BY bridge_score DESC, p.citationCount DESC
            LIMIT $top_k
        """, method_ids=list(methods.keys()),
             dataset_ids=list(datasets.keys()),
             top_k=top_k)
        return [dict(r) for r in result]


def format_results(query, results):
    print(f"\nQuery: {query!r}")
    print("-" * 80)
    if not results:
        print("  (no results)")
        return
    for i, r in enumerate(results, 1):
        title = (r["title"] or "")[:75]
        cites = r.get("citationCount") or 0
        year  = r.get("year") or "?"
        print(f"{i:2}. [bridge={r['bridge_score']}  m={r['method_hits']} d={r['dataset_hits']}]  "
              f"{year}  ({cites:>4} cites)")
        print(f"     {title}")
        if r["hit_methods"]:
            print(f"     methods: {r['hit_methods']}")
        if r["hit_datasets"]:
            print(f"     datasets: {r['hit_datasets']}")


# Same probes as retrieve_vector.py for side-by-side comparison
TEST_QUERIES = [
    "knowledge graph augmented retrieval for question answering",
    "dense passage retrieval with hard negative mining",
    "long-context retrieval for legal document analysis",
    "self-correcting retrieval augmented generation",
    "evaluation framework for RAG hallucination detection",
]


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PWD))

    for q in TEST_QUERIES:
        print(f"\nQuery: {q!r}")
        results = graph_search(driver, q, top_k=5, verbose=True)
        format_results(q, results)

    driver.close()
    print("\n[Gate 4 complete]  Next: retrieve_dual.py for RRF fusion of vector + graph.")


if __name__ == "__main__":
    main()