"""Day 7 helper - interactively populate relevant_paperIds for gold_questions.jsonl

For each question with empty relevant_paperIds, runs dual_search top-20,
prints results with titles, prompts you to mark relevant indices. Saves
the file after each question so quitting mid-session loses nothing.

Usage:
    python src/build_gold.py                # process all unannotated questions
    python src/build_gold.py q03            # process only q03
    python src/build_gold.py q03 --review   # re-annotate q03 even if already populated
"""
import argparse
import os
import json
import logging
from pathlib import Path

logging.getLogger("neo4j").setLevel(logging.ERROR)

from neo4j import GraphDatabase
from dotenv import load_dotenv

from retrieve_vector import get_model
from retrieve_dual import dual_search

load_dotenv()

URI  = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PWD  = os.getenv("NEO4J_PASSWORD")

GOLD_FILE = Path("eval/gold_questions.jsonl")
TOP_K_SHOW = 20  # candidates to display per question


def load_questions():
    questions = []
    with open(GOLD_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions


def save_questions(questions):
    GOLD_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(GOLD_FILE, "w", encoding="utf-8") as f:
        for q in questions:
            f.write(json.dumps(q) + "\n")


def annotate_question(driver, q, top_k=TOP_K_SHOW):
    print(f"\n{'='*84}")
    print(f"Question {q['id']}: {q['question']}")
    print(f"Topic: {q['topic']}  |  Regime: {q['regime']}")
    if q.get("relevant_paperIds"):
        print(f"Already annotated with {len(q['relevant_paperIds'])} papers (use --review to redo)")
    print(f"{'='*84}")

    results = dual_search(driver, q["question"], top_k=top_k, verbose=False)
    if not results:
        print("  No retrieval results - cannot annotate.")
        return q

    for i, r in enumerate(results, 1):
        title = (r["title"] or "")[:78]
        cites = r.get("citationCount") or 0
        year  = r.get("year") or "?"
        v_r   = f"v#{r['vector_rank']}" if r.get("vector_rank") else "v#-"
        g_r   = f"g#{r['graph_rank']}"  if r.get("graph_rank")  else "g#-"
        print(f"  {i:2}. ({year}, {cites:>4} cites)  [{v_r} {g_r}]  {title}")

    print(f"\nMark relevant papers (indices 1-{top_k}, space-separated)")
    print("  Example: '1 3 5 7'  (mark papers at those positions as relevant)")
    print("  's' = skip this question for now")
    print("  'q' = quit without saving this question")

    user_input = input("> ").strip()
    if user_input.lower() == "q":
        return None
    if user_input.lower() == "s":
        return q

    try:
        indices = [int(x) for x in user_input.split() if x.strip().isdigit()]
        relevant_pids = [results[i-1]["paperId"] for i in indices if 1 <= i <= len(results)]
    except (ValueError, IndexError) as e:
        print(f"  Invalid input ({e}) - skipping.")
        return q

    if not relevant_pids:
        print("  No valid indices - skipping.")
        return q

    q["relevant_paperIds"] = relevant_pids

    print(f"  Saved {len(relevant_pids)} relevant papers:")
    for i, pid in zip(indices, relevant_pids):
        title = (results[i-1]["title"] or "")[:70]
        print(f"    {i}. {title}")

    notes = input("Optional notes for this question (Enter to skip): ").strip()
    if notes:
        q["notes"] = notes

    return q


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("question_id", nargs="?", default=None, help="Specific question ID to annotate")
    parser.add_argument("--review", action="store_true", help="Re-annotate even if already populated")
    args = parser.parse_args()

    driver = GraphDatabase.driver(URI, auth=(USER, PWD))
    print("Loading BGE-base...")
    get_model()
    print("  Ready.")

    questions = load_questions()

    targets = []
    for q in questions:
        if args.question_id and q["id"] != args.question_id:
            continue
        if not args.review and q["relevant_paperIds"]:
            continue
        targets.append(q)

    if not targets:
        print("\nNo questions to annotate (use --review to re-annotate existing).")
        driver.close()
        return

    print(f"\nQuestions to annotate: {[q['id'] for q in targets]}")

    for q in targets:
        # Locate q in the master list for save-back
        for i, existing in enumerate(questions):
            if existing["id"] == q["id"]:
                updated = annotate_question(driver, q)
                if updated is None:
                    print("\nQuitting. Changes through last save are preserved.")
                    save_questions(questions)
                    driver.close()
                    return
                questions[i] = updated
                save_questions(questions)  # save after every question
                break

    driver.close()
    print(f"\nDone. Annotated questions saved to {GOLD_FILE}")
    print("Next: python src/eval_retrieval.py")


if __name__ == "__main__":
    main()