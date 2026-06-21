"""Day 5 Gate 3 - Vector-only retrieval over Paper embeddings.

Takes a query string, embeds it with BGE-base (using the asymmetric query prefix),
and uses Neo4j's native vector index to find the top-k most similar papers.

CRITICAL: BGE-base is an ASYMMETRIC embedding model.
- Documents (Gate 1): encoded WITHOUT a prefix.
- Queries (this script): encoded WITH the prefix
  "Represent this sentence for searching relevant passages: "
Skipping the query prefix drops retrieval quality noticeably. Do not remove it.

This module also exposes `vector_search(driver, query, top_k)` and `embed_query(query)`
as importable functions, so retrieve_dual.py can reuse them without reloading
the 440MB BGE model.
"""
import os
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

URI  = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PWD  = os.getenv("NEO4J_PASSWORD")

MODEL_NAME   = "BAAI/bge-base-en-v1.5"
INDEX_NAME   = "paper_embedding_idx"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Module-level singleton - load model once, reuse across calls
_model = None

def get_model():
    """Lazy-load BGE-base on first use, then cache."""
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_query(query: str):
    """Embed a query string with BGE-base, applying the asymmetric query prefix."""
    model = get_model()
    return model.encode(
        QUERY_PREFIX + query,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).tolist()


def vector_search(driver, query: str, top_k: int = 10):
    """Return top-k Paper records ranked by cosine similarity to query.

    Returns a list of dicts: {paperId, title, year, citationCount, score}.
    Score is cosine similarity in [-1, 1]; for normalized BGE embeddings most
    results land in [0.4, 0.8].
    """
    query_emb = embed_query(query)
    with driver.session() as s:
        result = s.run(
            """
            CALL db.index.vector.queryNodes($index_name, $top_k, $query_emb)
            YIELD node, score
            RETURN node.paperId       AS paperId,
                   node.title         AS title,
                   node.year          AS year,
                   node.citationCount AS citationCount,
                   score
            ORDER BY score DESC
            """,
            index_name=INDEX_NAME,
            top_k=top_k,
            query_emb=query_emb,
        )
        return [dict(r) for r in result]


def format_results(query, results):
    print(f"\nQuery: {query!r}")
    print("-" * 80)
    for i, r in enumerate(results, 1):
        title = (r["title"] or "")[:75]
        cites = r.get("citationCount") or 0
        year  = r.get("year") or "?"
        print(f"{i:2}. [{r['score']:.4f}]  {year}  ({cites:>4} cites)")
        print(f"     {title}")


# Hand-written probes covering different RAG sub-topics
TEST_QUERIES = [
    "knowledge graph augmented retrieval for question answering",
    "dense passage retrieval with hard negative mining",
    "long-context retrieval for legal document analysis",
    "self-correcting retrieval augmented generation",
    "evaluation framework for RAG hallucination detection",
]


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PWD))
    print(f"Loading model: {MODEL_NAME}")
    get_model()
    print("  Model loaded.")

    for q in TEST_QUERIES:
        results = vector_search(driver, q, top_k=5)
        format_results(q, results)

    driver.close()
    print("\n[Gate 3 complete]  If top results look on-topic, proceed to retrieve_graph.py.")


if __name__ == "__main__":
    main()