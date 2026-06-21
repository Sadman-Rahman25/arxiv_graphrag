"""Day 6 - Format retrieval results into LLM-ready context block.

Takes the output of dual_search() (which contains paperId + metadata but no
abstract) and joins it with abstract data pulled from Neo4j. Produces a
single formatted text block ready to inject into the LLM prompt, plus a
lookup dict mapping [P1], [P2]... tags back to paperIds for citation
resolution after generation.

Design choices:
- Use [P1]..[PK] tags for in-prompt references (not raw paperIds) since
  S2 paperIds are long hash strings the LLM may misquote or truncate.
- Truncate abstracts to ABSTRACT_CHARS chars to bound prompt size.
- Include matched_methods in context so the LLM can leverage graph signal
  in its reasoning.
"""
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

URI  = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PWD  = os.getenv("NEO4J_PASSWORD")

ABSTRACT_CHARS = 600


def fetch_abstracts(driver, paper_ids):
    """Pull abstract + venue for a list of paperIds.

    Returns dict {paperId -> {abstract, venue}}.
    """
    if not paper_ids:
        return {}
    with driver.session() as s:
        rows = s.run("""
            MATCH (p:Paper)
            WHERE p.paperId IN $ids
            OPTIONAL MATCH (p)-[:PUBLISHED_AT]->(v:Venue)
            RETURN p.paperId AS paperId,
                   p.abstract AS abstract,
                   v.name AS venue
        """, ids=paper_ids)
        return {r["paperId"]: {"abstract": r["abstract"], "venue": r["venue"]} for r in rows}


def format_context(driver, retrieval_results, abstract_chars=ABSTRACT_CHARS):
    """Build LLM-ready context block from retrieval results.

    Args:
        driver: Neo4j driver
        retrieval_results: list of dicts from dual_search()
        abstract_chars: max chars per abstract (truncated at word boundary)

    Returns:
        (context_text, lookup) where lookup maps tag string -> paperId.
        e.g. {"P1": "abc123...", "P2": "def456..."}
    """
    if not retrieval_results:
        return "", {}

    pids = [r["paperId"] for r in retrieval_results]
    abstracts = fetch_abstracts(driver, pids)

    lines = []
    lookup = {}
    for i, r in enumerate(retrieval_results, 1):
        tag = f"P{i}"
        lookup[tag] = r["paperId"]
        meta = abstracts.get(r["paperId"], {})
        abstract = (meta.get("abstract") or "").strip()
        if abstract and len(abstract) > abstract_chars:
            abstract = abstract[:abstract_chars].rsplit(" ", 1)[0] + "..."
        venue = meta.get("venue") or "unknown venue"
        methods = r.get("hit_methods") or []
        methods_str = ", ".join(methods) if methods else "none"
        cites = r.get("citationCount") or 0
        year = r.get("year") or "?"

        lines.append(
            f"[{tag}] {r['title']}\n"
            f"     {year} | {venue} | {cites:,} citations | methods: {methods_str}\n"
            f"     Abstract: {abstract or '(no abstract available)'}\n"
        )

    return "\n".join(lines), lookup


if __name__ == "__main__":
    # Smoke test - prints the context block for one query
    import logging
    logging.getLogger("neo4j").setLevel(logging.ERROR)
    from retrieve_vector import get_model
    from retrieve_dual import dual_search

    driver = GraphDatabase.driver(URI, auth=(USER, PWD))
    print("Loading model...")
    get_model()
    print("  Ready.")

    test_query = "how does Self-RAG decide when to retrieve"
    print(f"\nQuery: {test_query}")
    results = dual_search(driver, test_query, top_k=5, verbose=False)
    context, lookup = format_context(driver, results)

    print(f"\nContext block ({len(context):,} chars, {len(lookup)} papers):\n")
    print(context)
    print(f"\nLookup: {lookup}")
    driver.close()