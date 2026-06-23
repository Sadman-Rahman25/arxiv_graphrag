"""Day 8 - Generate answers for all gold questions using dual retriever.

For each question in eval/gold_questions.jsonl, runs:
  dual_search -> format_context -> generate_cited_answer
and saves the full record to eval/generated_answers.jsonl.

Leans on Day 6 cache, so reruns are free unless the prompt/retrieval changes.
Idempotent: skips questions already in the output file.

Usage:
    python src/generate_eval_answers.py
    python src/generate_eval_answers.py --top-k 10
    python src/generate_eval_answers.py --retriever vector
"""
import argparse
import os
import json
import logging
from pathlib import Path

logging.getLogger("neo4j").setLevel(logging.ERROR)

from neo4j import GraphDatabase
from dotenv import load_dotenv

from retrieve_vector  import vector_search, get_model
from retrieve_graph   import graph_search
from retrieve_dual    import dual_search
from format_context   import format_context
from generate_answer  import generate_cited_answer, DEFAULT_MODEL

load_dotenv()

URI  = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PWD  = os.getenv("NEO4J_PASSWORD")

GOLD_FILE   = Path("eval/gold_questions.jsonl")
OUTPUT_FILE = Path("eval/generated_answers.jsonl")
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_existing():
    if not OUTPUT_FILE.exists():
        return {}
    cache = {}
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                key = f"{rec['question_id']}__{rec['retriever']}"
                cache[key] = rec
            except (json.JSONDecodeError, KeyError):
                continue
    return cache


def append_record(record):
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def retrieve(driver, query, retriever_name, top_k):
    if retriever_name == "vector":
        return vector_search(driver, query, top_k=top_k)
    elif retriever_name == "graph":
        return graph_search(driver, query, top_k=top_k, verbose=False)
    elif retriever_name == "dual":
        return dual_search(driver, query, top_k=top_k, verbose=False)
    else:
        raise ValueError(f"unknown retriever: {retriever_name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k",     type=int, default=10)
    parser.add_argument("--retriever", choices=["vector", "graph", "dual"], default="dual")
    parser.add_argument("--model",     default=DEFAULT_MODEL)
    parser.add_argument("--force",     action="store_true")
    args = parser.parse_args()

    driver = GraphDatabase.driver(URI, auth=(USER, PWD))
    print("Loading BGE-base...")
    get_model()
    print("  Ready.\n")

    with open(GOLD_FILE, encoding="utf-8") as f:
        questions = [json.loads(line) for line in f if line.strip()]

    existing = load_existing()
    print(f"Loaded {len(questions)} gold questions; "
          f"{len(existing)} answers already in {OUTPUT_FILE}\n")

    for q in questions:
        key = f"{q['id']}__{args.retriever}"
        if not args.force and key in existing:
            print(f"  {q['id']} [{args.retriever}]  skip (cached)")
            continue

        print(f"  {q['id']} [{args.retriever}]  generating...")

        results = retrieve(driver, q["question"], args.retriever, args.top_k)

        for r in results:
            r.setdefault("hit_methods",  [])
            r.setdefault("hit_datasets", [])
            r.setdefault("bridge_score", 0)
            r.setdefault("vector_rank",  None)
            r.setdefault("graph_rank",   None)

        if not results:
            record = {
                "question_id": q["id"], "question": q["question"],
                "retriever": args.retriever, "retrieved": [],
                "context_len": 0, "lookup": {},
                "answer": None, "citations": [], "confidence": "abstain",
                "model": args.model, "cached": False,
            }
            append_record(record)
            print(f"      ABSTAIN (no retrieval)")
            continue

        context, lookup = format_context(driver, results)
        response = generate_cited_answer(q["question"], context, model=args.model)

        record = {
            "question_id": q["id"], "question": q["question"],
            "retriever": args.retriever,
            "retrieved": [{"paperId": r["paperId"], "title": r["title"],
                           "year": r["year"], "citationCount": r["citationCount"]}
                          for r in results],
            "context_len": len(context), "lookup": lookup,
            "answer": response["answer"], "citations": response["citations"],
            "confidence": response["confidence"],
            "model": response["model"], "cached": response.get("cached", False),
        }
        append_record(record)
        cache_tag = "(cached)" if response.get("cached") else "(fresh)"
        print(f"      {cache_tag}  conf={response['confidence']}  "
              f"cites={len(response['citations'])}")

    driver.close()
    print(f"\nDone. Answers saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()