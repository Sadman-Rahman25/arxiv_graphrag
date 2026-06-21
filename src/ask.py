"""Day 6 - End-to-end Q&A CLI.

Usage:
    python src/ask.py "your question here"
    python src/ask.py "question" --top-k 10 --model llama-3.3-70b-versatile
    python src/ask.py "question" --no-cache

Pipeline:
    1. Retrieve top-K papers via dual_search (vector + graph + adaptive RRF)
    2. Abstain if no papers found (Gate 4 abstention guardrail)
    3. Format retrieved papers as LLM context block
    4. Generate answer with citation contract via Groq
    5. Resolve [Pn] tags back to paperIds and titles
    6. Print formatted answer + reference list + confidence
"""
import argparse
import os
import logging
import re

logging.getLogger("neo4j").setLevel(logging.ERROR)

from neo4j import GraphDatabase
from dotenv import load_dotenv

from retrieve_vector  import get_model
from retrieve_dual    import dual_search
from format_context   import format_context
from generate_answer  import generate_cited_answer, DEFAULT_MODEL

load_dotenv()

URI  = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PWD  = os.getenv("NEO4J_PASSWORD")


def resolve_citations(answer_text, lookup, retrieval_results):
    """Find all P-tags in the answer (including cluster citations like [P1, P3])."""
    tags_in_order = []
    seen = set()
    # Walk each bracket group left-to-right, then each P-tag within it
    for bracket_match in re.finditer(r"\[([^\]]+)\]", answer_text):
        for p_match in re.finditer(r"P(\d+)", bracket_match.group(1)):
            tag = f"P{p_match.group(1)}"
            if tag not in seen and tag in lookup:
                seen.add(tag)
                tags_in_order.append(tag)

    pid_to_result = {r["paperId"]: r for r in retrieval_results}
    refs = []
    for tag in tags_in_order:
        pid = lookup[tag]
        r = pid_to_result.get(pid, {})
        refs.append({
            "tag":     tag,
            "paperId": pid,
            "title":   r.get("title", "(unknown)"),
            "year":    r.get("year"),
            "citationCount": r.get("citationCount"),
        })
    return refs


def ask(question, top_k=10, model=DEFAULT_MODEL, use_cache=True):
    driver = GraphDatabase.driver(URI, auth=(USER, PWD))
    print(f"Question: {question}\n")

    # 1. Retrieve
    print("[1/3] Retrieving...")
    results = dual_search(driver, question, top_k=top_k, verbose=False)

    # Gate 4: abstention guardrail
    if not results:
        print("\n[ABSTAIN]  No relevant papers found in corpus. Cannot answer.")
        driver.close()
        return None
    print(f"      Got {len(results)} papers, top RRF={results[0]['rrf_score']:.4f}")

    # 2. Format context
    print("[2/3] Formatting context...")
    context, lookup = format_context(driver, results)
    print(f"      Context: {len(context):,} chars, {len(lookup)} paper tags")

    # 3. Generate
    print(f"[3/3] Generating answer (model={model})...")
    response = generate_cited_answer(question, context, model=model, use_cache=use_cache)
    cache_status = "(cached)" if response.get("cached") else "(fresh)"
    print(f"      {cache_status}  confidence={response['confidence']}")

    # 4. Resolve citations
    refs = resolve_citations(response["answer"], lookup, results)

    # Print final
    print("\n" + "=" * 80)
    print("ANSWER")
    print("=" * 80)
    print(response["answer"])

    if refs:
        print("\n" + "-" * 80)
        print(f"REFERENCES ({len(refs)} cited of {len(results)} retrieved)")
        print("-" * 80)
        for ref in refs:
            cites = ref.get("citationCount") or 0
            year  = ref.get("year") or "?"
            print(f"[{ref['tag']}] {ref['title']}")
            print(f"      {year}  |  {cites:,} citations  |  paperId: {ref['paperId']}")

    print(f"\n[confidence: {response['confidence']}]")
    driver.close()
    return response


def main():
    parser = argparse.ArgumentParser(description="End-to-end Q&A over RAG paper corpus")
    parser.add_argument("question", help="Question to answer")
    parser.add_argument("--top-k", type=int, default=10, help="Number of papers to retrieve (default: 10)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Groq model (default: {DEFAULT_MODEL})")
    parser.add_argument("--no-cache", action="store_true", help="Bypass LLM cache")
    args = parser.parse_args()

    print("Loading BGE-base (singleton)...")
    get_model()
    print("  Ready.\n")

    ask(args.question, top_k=args.top_k, model=args.model, use_cache=not args.no_cache)


if __name__ == "__main__":
    main()