"""Day 5 Gate 5 - Dual-pattern retriever with adaptive RRF.

KEY CHANGE from v1: graph_weight is computed per-query based on the number
of entities the gazetteer matched in the query string.

Adaptive weighting:
  0 entities matched -> graph_weight = 0.0 (graph contributes nothing)
  1 entity  matched -> graph_weight = 0.7 (low trust; vector should dominate)
  2+ entities matched -> graph_weight = 1.5 (high trust per Day 4)
"""
import os
import logging

logging.getLogger("neo4j").setLevel(logging.ERROR)

from neo4j import GraphDatabase
from dotenv import load_dotenv

from retrieve_vector import vector_search, get_model
from retrieve_graph  import graph_search, extract_entities_from_query

load_dotenv()

URI  = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PWD  = os.getenv("NEO4J_PASSWORD")

K_RRF         = 60
VECTOR_WEIGHT = 1.0
GRAPH_WEIGHT_SINGLE = 0.7
GRAPH_WEIGHT_MULTI  = 1.5
CANDIDATES    = 20
FINAL_K       = 10


def compute_graph_weight(matched_methods, matched_datasets):
    total = len(matched_methods) + len(matched_datasets)
    if total == 0:
        return 0.0
    elif total == 1:
        return GRAPH_WEIGHT_SINGLE
    else:
        return GRAPH_WEIGHT_MULTI


def dual_search(driver, query, top_k=FINAL_K, candidates=CANDIDATES, verbose=True):
    matched_methods, matched_datasets = extract_entities_from_query(driver, query)
    graph_weight = compute_graph_weight(matched_methods, matched_datasets)

    if verbose:
        print(f"  Matched: {len(matched_methods)} method(s) {sorted(matched_methods.keys())}, "
              f"{len(matched_datasets)} dataset(s) {sorted(matched_datasets.keys())}")
        print(f"  Adaptive graph_weight = {graph_weight}")

    v_results = vector_search(driver, query, top_k=candidates)
    g_results = graph_search(driver, query, top_k=candidates, verbose=False) \
                if (matched_methods or matched_datasets) else []

    v_rank = {r["paperId"]: i + 1 for i, r in enumerate(v_results)}
    g_rank = {r["paperId"]: i + 1 for i, r in enumerate(g_results)}

    paper_meta = {}
    for r in v_results:
        paper_meta[r["paperId"]] = {
            "title": r["title"], "year": r["year"],
            "citationCount": r["citationCount"],
            "vector_score": r["score"],
        }
    for r in g_results:
        pid = r["paperId"]
        meta = paper_meta.setdefault(pid, {
            "title": r["title"], "year": r["year"],
            "citationCount": r["citationCount"],
        })
        meta["bridge_score"] = r["bridge_score"]
        meta["hit_methods"]  = r.get("hit_methods", [])
        meta["hit_datasets"] = r.get("hit_datasets", [])

    rrf_scores = {}
    for pid in set(v_rank) | set(g_rank):
        s = 0.0
        if pid in v_rank: s += VECTOR_WEIGHT / (K_RRF + v_rank[pid])
        if pid in g_rank: s += graph_weight  / (K_RRF + g_rank[pid])
        rrf_scores[pid] = s

    ranked = sorted(rrf_scores.items(), key=lambda x: -x[1])[:top_k]

    out = []
    for pid, score in ranked:
        m = paper_meta[pid]
        out.append({
            "paperId": pid, "title": m["title"], "year": m["year"],
            "citationCount": m["citationCount"],
            "rrf_score": score,
            "vector_rank": v_rank.get(pid),
            "graph_rank":  g_rank.get(pid),
            "vector_score": m.get("vector_score"),
            "bridge_score": m.get("bridge_score"),
            "hit_methods":  m.get("hit_methods", []),
            "hit_datasets": m.get("hit_datasets", []),
        })
    return out


def format_results(query, results):
    print(f"\nQuery: {query!r}")
    print("=" * 80)
    if not results:
        print("  (no results)")
        return
    for i, r in enumerate(results, 1):
        title = (r["title"] or "")[:72]
        cites = r.get("citationCount") or 0
        year  = r.get("year") or "?"
        v_r   = f"v#{r['vector_rank']}" if r["vector_rank"] else "v#-"
        g_r   = f"g#{r['graph_rank']}"  if r["graph_rank"]  else "g#-"
        regime = "B" if r["vector_rank"] and r["graph_rank"] else ("V" if r["vector_rank"] else "G")
        print(f"{i:2}. [{regime}] [rrf={r['rrf_score']:.4f}  {v_r:>5} {g_r:>5}]  "
              f"{year}  ({cites:>4} cites)")
        print(f"     {title}")
        if r["hit_methods"]:
            print(f"     methods: {r['hit_methods']}")


TEST_QUERIES = [
    "knowledge graph augmented retrieval for question answering",
    "dense passage retrieval with hard negative mining",
    "long-context retrieval for legal document analysis",
    "self-correcting retrieval augmented generation",
    "evaluation framework for RAG hallucination detection",
]


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PWD))
    print("Loading BGE-base (singleton)...")
    get_model()
    print("  Ready.\n")
    print(f"RRF config: k={K_RRF}, vector_w={VECTOR_WEIGHT}, "
          f"graph_w_single={GRAPH_WEIGHT_SINGLE}, graph_w_multi={GRAPH_WEIGHT_MULTI}, "
          f"candidates={CANDIDATES}")
    print(f"Regime tag: [B]=both retrievers, [V]=vector-only, [G]=graph-only")

    for q in TEST_QUERIES:
        results = dual_search(driver, q, top_k=5, verbose=True)
        format_results(q, results)

    driver.close()
    print("\n[Gate 5 v2 complete]")


if __name__ == "__main__":
    main()