"""Day 7 - Evaluate retrieval quality across three retrievers.

Loads eval/gold_questions.jsonl. For each annotated question (has relevant_paperIds),
runs vector-only, graph-only, and dual retrieval, then computes:
  - Recall@5, Recall@10: fraction of gold relevants in top-K
  - MRR: 1 / rank of first gold relevant result (0 if none in top-K)

Per-query results and aggregate means are printed and saved to
eval/results/retrieval_eval_<timestamp>.json for later analysis.

Methodology: gold relevance is INCOMPLETE (we mark "must-find" papers, not
all relevant papers). Recall@K is primary because Precision@K penalizes
finding relevant-but-unannotated papers - common in IR benchmarks with
sparse judgments (TREC, BEIR follow this pattern).
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime

logging.getLogger("neo4j").setLevel(logging.ERROR)

from neo4j import GraphDatabase
from dotenv import load_dotenv

from retrieve_vector import vector_search, get_model
from retrieve_graph  import graph_search
from retrieve_dual   import dual_search

load_dotenv()

URI  = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PWD  = os.getenv("NEO4J_PASSWORD")

GOLD_FILE   = Path("eval/gold_questions.jsonl")
RESULTS_DIR = Path("eval/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

EVAL_K = 10  # evaluate top-K


def recall_at_k(retrieved_pids, gold_pids, k):
    """Fraction of gold relevants in top-K. None if no gold."""
    if not gold_pids:
        return None
    top_k = retrieved_pids[:k]
    hits = len(set(top_k) & set(gold_pids))
    return hits / len(gold_pids)


def reciprocal_rank(retrieved_pids, gold_pids):
    """1 / rank of first gold relevant, or 0."""
    gold_set = set(gold_pids)
    for i, pid in enumerate(retrieved_pids, 1):
        if pid in gold_set:
            return 1.0 / i
    return 0.0


def evaluate_one(driver, question, k=EVAL_K):
    """Run all three retrievers and compute metrics for one question."""
    gold_pids = set(question["relevant_paperIds"])
    if not gold_pids:
        return None

    q_text = question["question"]

    v_results = vector_search(driver, q_text, top_k=k)
    g_results = graph_search(driver, q_text, top_k=k, verbose=False)
    d_results = dual_search(driver, q_text, top_k=k, verbose=False)

    v_pids = [r["paperId"] for r in v_results]
    g_pids = [r["paperId"] for r in g_results]
    d_pids = [r["paperId"] for r in d_results]

    def metrics(pids):
        return {
            "recall@5":  recall_at_k(pids, gold_pids, 5),
            "recall@10": recall_at_k(pids, gold_pids, 10),
            "mrr":       reciprocal_rank(pids, gold_pids),
            "top_pids":  pids,
        }

    return {
        "id":         question["id"],
        "topic":      question["topic"],
        "regime":     question["regime"],
        "gold_count": len(gold_pids),
        "vector":     metrics(v_pids),
        "graph":      metrics(g_pids),
        "dual":       metrics(d_pids),
    }


def aggregate(per_query_results):
    """Mean metrics across queries."""
    agg = {}
    for retriever in ("vector", "graph", "dual"):
        agg[retriever] = {}
        for metric in ("recall@5", "recall@10", "mrr"):
            values = [
                r[retriever][metric]
                for r in per_query_results
                if r[retriever][metric] is not None
            ]
            agg[retriever][metric] = sum(values) / len(values) if values else 0.0
    return agg


def format_aggregate(agg):
    lines = []
    lines.append(f"{'Retriever':<10}  {'Recall@5':<10}  {'Recall@10':<10}  {'MRR':<10}")
    lines.append("-" * 46)
    for retriever in ("vector", "graph", "dual"):
        r = agg[retriever]
        lines.append(
            f"{retriever:<10}  "
            f"{r['recall@5']:<10.3f}  "
            f"{r['recall@10']:<10.3f}  "
            f"{r['mrr']:<10.3f}"
        )
    return "\n".join(lines)


def format_per_query(per_query_results):
    lines = []
    lines.append(f"{'ID':<5} {'Regime':<28} {'V R@10':>7} {'G R@10':>7} {'D R@10':>7}  {'Winner'}")
    lines.append("-" * 78)
    for r in per_query_results:
        vr = r["vector"]["recall@10"] or 0
        gr = r["graph"]["recall@10"] or 0
        dr = r["dual"]["recall@10"] or 0
        scores = [("V", vr), ("G", gr), ("D", dr)]
        max_score = max(s[1] for s in scores)
        winners = [name for name, s in scores if s == max_score]
        winner = "/".join(winners) if len(winners) > 1 else winners[0]
        lines.append(
            f"{r['id']:<5} {r['regime'][:28]:<28} "
            f"{vr:>7.3f} {gr:>7.3f} {dr:>7.3f}  {winner}"
        )
    return "\n".join(lines)


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PWD))
    print("Loading BGE-base...")
    get_model()
    print("  Ready.\n")

    with open(GOLD_FILE, encoding="utf-8") as f:
        questions = [json.loads(line) for line in f if line.strip()]

    annotated   = [q for q in questions if q["relevant_paperIds"]]
    unannotated = [q for q in questions if not q["relevant_paperIds"]]

    print(f"Loaded {len(questions)} questions: "
          f"{len(annotated)} annotated, {len(unannotated)} unannotated")
    if unannotated:
        print(f"  Skipping unannotated: {[q['id'] for q in unannotated]}")
    if not annotated:
        print("\nNo annotated questions. Run python src/build_gold.py first.")
        driver.close()
        return

    print(f"\nEvaluating {len(annotated)} questions across vector/graph/dual (k={EVAL_K})...")
    per_query = []
    for q in annotated:
        result = evaluate_one(driver, q)
        if result:
            per_query.append(result)
            print(f"  {q['id']:<5} done (gold_count={result['gold_count']})")

    agg = aggregate(per_query)

    print("\n" + "=" * 78)
    print("AGGREGATE METRICS (mean across {} queries)".format(len(per_query)))
    print("=" * 78)
    print(format_aggregate(agg))

    print("\n" + "=" * 78)
    print("PER-QUERY RESULTS (Recall@10)")
    print("=" * 78)
    print(format_per_query(per_query))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = RESULTS_DIR / f"retrieval_eval_{ts}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp":            ts,
            "questions_evaluated":  len(per_query),
            "questions_skipped":    len(unannotated),
            "eval_k":               EVAL_K,
            "aggregate":            agg,
            "per_query":            per_query,
        }, f, indent=2)
    print(f"\nFull results saved to {out_file}")

    driver.close()


if __name__ == "__main__":
    main()