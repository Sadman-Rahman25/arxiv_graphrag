# Day 4 — Sunday, June 21, 2026

## Status: COMPLETE (all 8 gates green)

## Graph state
- Paper:   3,500
- Method:    157
- Dataset:    47
- Author: 16,976  (from 21,088 author slots — 19.5% dedup rate)
- Venue:     862

## Edges
- AUTHORED_BY:     21,082
- MENTIONS_METHOD:  5,255  (avg 1.5 methods/paper)
- CITES:            4,195
- PUBLISHED_AT:     3,417
- MENTIONS_DATASET:   321
- USES_METHOD:         41  (LLM-extracted)
- INTRODUCES_METHOD:   19  (LLM-extracted)
- EVALUATED_ON:        11  (LLM-extracted)
- INTRODUCES_DATASET:   2  (LLM-extracted)

## Constraints + indexes
- 5 uniqueness constraints (Paper.paperId, Method.id, Dataset.id, Author.authorId, Venue.name)
- 4 supporting indexes (Method.category, Dataset.category, Paper.citationCount, Paper.year)

## Key finding: citation density is lower than scoped
- Estimated CITES: 20K–40K. Actual: 4,195.
- Reason: high-citation 2022–2026 papers mostly reference older foundational
  work that doesn't meet the citationCount≥5 in-window cutoff. The intra-corpus
  citation overlap is thinner than the broad reference count (66,089) suggested.

### CITES outdegree distribution
- 0 cites out: 2,520 papers (72%)
- 1 cite out:    272 papers (7.8%)
- 2–5 cites:     486 papers (13.9%)
- 6+ cites:      222 papers (6.3%)

The graph is hub-and-spoke on citations: ~700 papers carry the entire
citation-bridge retrieval pattern; the other 2,800 are reachable only via
method/dataset mentions or vector search.

## Engineering implication for Day 5
- Method-bridge dominates citation-bridge for multi-hop retrieval.
- 92.7% of papers connect through ≥1 method node vs ~44% through citations.
- Dual-pattern retriever should weight method-bridge paths higher than
  citation-bridge paths. Citation-bridge stays useful for the ~700-paper
  hub subgraph (canonical-paper-finding queries).

## Multi-hop sanity check
Seed = `rag` (most-mentioned method). Top co-mentioned via citation:
gpt35 (408), gpt4 (333), knowledge_graph (248), self_rag (177),
graphrag (107), mistral (74), ragas (63), flare (62), bm25 (52),
contriever (51). Tight semantic neighborhood — graph structure is
carrying signal.

## Orphans (acceptable, documented)
- 2 papers w/o author          (S2 metadata gaps)
- 83 papers w/o venue          (preprints without venue field)
- 255 papers w/o method mention (Day 3 gazetteer + LLM gap; will narrow as
                                 LLM extraction runs in background)
- 1,953 papers w/o CITES        (expected from density finding above)
- 39 methods w/ zero mentions   (gazetteer entries; candidates for pruning)
- 10 datasets w/ zero mentions  (gazetteer entries; candidates for pruning)

## Files added today
- src/ingest_constraints.py
- src/ingest_papers.py
- src/ingest_methods_datasets.py
- src/ingest_mentions.py
- src/ingest_cites.py
- src/ingest_llm_edges.py
- src/ingest_authors_venues.py
- src/validate_graph.py

## Pending for Day 5
- [ ] Build Paper embeddings with BGE-base (768-dim) on title+abstract
- [ ] Create Neo4j vector index on Paper.embedding
- [ ] Implement dual-pattern retriever: vector + graph traversal
- [ ] Weight method-bridge traversal higher than citation-bridge per Day 4 finding
- [ ] First end-to-end Q→context flow on 5 hand-written test queries
- [ ] Background: continue run_llm_full.py to grow LLM extraction coverage