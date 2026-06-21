# Day 5 — Monday, June 22, 2026

## Status: COMPLETE (all 6 gates green)

## Gates
- [x] BGE-base embeddings for all 3,500 papers (768-dim, normalized)
- [x] Neo4j vector index on Paper.embedding (cosine)
- [x] Vector-only retrieval working
- [x] Graph-only retrieval working (method-bridge via gazetteer)
- [x] Dual-pattern retriever with adaptive weighted RRF
- [x] End-to-end test on 5 hand-written queries

## What shipped
- src/embed_papers.py — BGE-base encoding, resumable JSONL cache, push to Neo4j
- src/create_vector_index.py — Neo4j 5.x native vector index, cosine, 768-dim
- src/retrieve_vector.py — vector search with BGE query prefix (singleton model)
- src/retrieve_graph.py — method/dataset bridge retrieval, gazetteer match
- src/retrieve_dual.py — adaptive weighted RRF fusion
- src/retrieve.py — CLI wrapper for ad-hoc queries
- data/embeddings/paper_embeddings.jsonl — 25 MB cache

## Adaptive RRF design
First baseline used a fixed graph_weight=1.5 (per Day 4 finding that method-bridge
dominates citation-bridge). Test queries revealed a noise leak: when only `rag`
(3,078 mentions, most-mentioned method) matches the query, graph search collapses
to "top-cited RAG papers by citation" — generic and not query-specific. With
weight=1.5, this generic content outranked vector's specific matches.

Fix: adaptive graph_weight based on entity match count:
- 0 entities -> 0.0  (graph contributes nothing, pure vector)
- 1 entity   -> 0.7  (low trust, vector dominates)
- 2+ entities -> 1.5 (high trust per Day 4)

Result: Queries 4 (self-correcting) and 5 (hallucination) went from "all generic
RAG papers" to "all on-topic specific papers". Query 1 (KG-QA) traded canonical
high-cite papers out of top-5 for more specific compound matches; both lists are
acceptable.

## Empirical retrieval timing
- BGE-base encoding: 37 min on CPU for 3,500 docs (1.6 docs/sec)
- Neo4j vector index population: ~10 seconds for 3,500 vectors
- Per-query latency: <100ms (vector + graph + fusion)
- Model load: ~30s, singleton-cached across queries

## Sample retrieval contrasts (5 hand-written queries)
- KG-QA: [B] HybridRAG, KG-Guided RAG, Simple is Effective; [V] D-RAG, GNN-Enhanced
- Hard negatives: [B] Multilingual Negative Sampling, Aggretriever, TriSampler (bridge=4)
- Legal: [V] all (graceful pure-vector, 0 entities matched)
- Self-correcting RAG: [B] Active Retrieval; [V] DPR-is-Retrieving, Hybrid, Evidence-aware
- RAG hallucination: [V] all - Enhancing RAG, Lynx, RAGTruth, LettuceDetect, Mitigating

## Known limitation (polish-pass candidate)
The adaptive weighting uses a flat threshold (1 vs 2+ entities). Queries with one
rare-but-specific method (like `knowledge_graph`, 201 mentions) get the same low
weight as queries with one over-common method (like `rag`, 3,078 mentions).
Inverse-frequency weighting would be a Day 11/12 polish improvement:
  graph_w = clamp(0.5, 1.5, 1.5 - log10(mentions / 100))

## Pending for Day 6
- [ ] Build the answer generator: Groq Llama-3.3-70B consumes retrieved papers
- [ ] Citation contract (structured JSON, paperId references)
- [ ] Context formatting: top-K papers with title + abstract + venue + cites
- [ ] Hallucination guardrails (refuse to answer when retrieval is weak)
- [ ] End-to-end: query -> retrieve -> generate cited answer