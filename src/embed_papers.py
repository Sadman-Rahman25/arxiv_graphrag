"""Day 5 Gate 1 - Generate BGE-base embeddings for all 3,500 papers.

Pipeline:
1. Fetch paperId, title, abstract from Neo4j (3,500 papers)
2. Build embedding text: title + abstract (fall back to title-only if no abstract)
3. Encode in batches of 32 with BAAI/bge-base-en-v1.5, normalized
4. Cache to data/embeddings/paper_embeddings.jsonl (resumable if interrupted)
5. Push back to Neo4j as Paper.embedding property
6. Verify count

Memory note: BGE-base ~440MB model, ~10MB total embeddings.
Expected wall time on CPU: 3-8 minutes for full corpus.
"""
import os
import json
import time
from pathlib import Path

from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

URI  = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PWD  = os.getenv("NEO4J_PASSWORD")

MODEL_NAME  = "BAAI/bge-base-en-v1.5"
BATCH_SIZE  = 32
PUSH_BATCH  = 100
OUTPUT_FILE = Path("data/embeddings/paper_embeddings.jsonl")
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)


def fetch_papers(driver):
    """Pull all papers with title + abstract from Neo4j, deterministic order."""
    with driver.session() as s:
        result = s.run("""
            MATCH (p:Paper)
            RETURN p.paperId AS paperId,
                   p.title   AS title,
                   p.abstract AS abstract
            ORDER BY p.paperId
        """)
        return [dict(r) for r in result]


def build_text(paper):
    """Title + abstract for document embedding.

    BGE-base does NOT need a query prefix for document encoding (only for queries,
    where you'd prepend 'Represent this sentence for searching relevant passages: ').
    """
    title    = (paper.get("title") or "").strip()
    abstract = (paper.get("abstract") or "").strip()
    if abstract:
        return f"{title}\n\n{abstract}"
    return title


def load_cache():
    """Return set of already-embedded paperIds from JSONL cache."""
    if not OUTPUT_FILE.exists():
        return set()
    cached = set()
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        for line in f:
            try:
                cached.add(json.loads(line)["paperId"])
            except (json.JSONDecodeError, KeyError):
                continue
    return cached


def append_to_cache(records):
    """Append fresh embeddings to JSONL cache."""
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for paper_id, emb in records:
            f.write(json.dumps({"paperId": paper_id, "embedding": emb.tolist()}) + "\n")


def push_to_neo4j(driver):
    """Read full JSONL cache, push embeddings to Neo4j in batches of 100."""
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        records = [json.loads(line) for line in f]
    print(f"  Loaded {len(records):,} embeddings from cache")

    with driver.session() as s:
        batch = []
        for record in tqdm(records, desc="Pushing to Neo4j"):
            batch.append(record)
            if len(batch) >= PUSH_BATCH:
                s.run("""
                    UNWIND $rows AS row
                    MATCH (p:Paper {paperId: row.paperId})
                    SET p.embedding = row.embedding
                """, rows=batch)
                batch = []
        if batch:
            s.run("""
                UNWIND $rows AS row
                MATCH (p:Paper {paperId: row.paperId})
                SET p.embedding = row.embedding
            """, rows=batch)


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PWD))

    print(f"Loading model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)
    print(f"  Model loaded. Embedding dim: {model.get_sentence_embedding_dimension()}")

    print("\nFetching papers from Neo4j...")
    papers = fetch_papers(driver)
    print(f"  Got {len(papers):,} papers")

    cached = load_cache()
    if cached:
        print(f"  Resume cache: {len(cached):,} papers already embedded, skipping those")

    todo = [p for p in papers if p["paperId"] not in cached]
    print(f"  To embed this run: {len(todo):,}")

    if todo:
        texts = [build_text(p) for p in todo]
        ids   = [p["paperId"] for p in todo]

        print(f"\nEncoding {len(texts):,} documents (batch={BATCH_SIZE})...")
        t0 = time.time()
        embeddings = model.encode(
            texts,
            batch_size=BATCH_SIZE,
            show_progress_bar=True,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        dt = time.time() - t0
        print(f"  Encoded in {dt:.1f}s ({len(texts)/dt:.1f} docs/sec)")

        append_to_cache(list(zip(ids, embeddings)))
        print(f"  Appended to {OUTPUT_FILE}")
    else:
        print("\nAll papers already embedded - skipping encoding.")

    print("\nPushing embeddings to Neo4j...")
    push_to_neo4j(driver)

    print("\nVerifying...")
    with driver.session() as s:
        with_emb    = s.run("MATCH (p:Paper) WHERE p.embedding IS NOT NULL RETURN count(p) AS c").single()["c"]
        total       = s.run("MATCH (p:Paper) RETURN count(p) AS c").single()["c"]
        sample_dim  = s.run("MATCH (p:Paper) WHERE p.embedding IS NOT NULL RETURN size(p.embedding) AS d LIMIT 1").single()
        print(f"  Papers with embedding: {with_emb:,} / {total:,}")
        if sample_dim:
            print(f"  Embedding dimension:   {sample_dim['d']}")

    driver.close()
    print("\n[Gate 1 complete]  Next: create_vector_index.py")


if __name__ == "__main__":
    main()