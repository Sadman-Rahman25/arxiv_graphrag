# Day 1 — June 20, 2026

## Environment
- Python 3.11.9 in D:\arxiv-graphrag\.venv
- Neo4j Desktop 2.1.4, instance arxiv-graphrag-db running 5.x
- APOC installed
- All required packages installed and verified

## Semantic Scholar query (LOCKED)

```python
QUERY = '"retrieval augmented generation" | "retrieval-augmented generation" | "dense passage retrieval" | RAG | GraphRAG | "dense retrieval"'
YEAR = '2022-2026'
FIELD_OF_STUDY = 'Computer Science'
EXPECTED_CANDIDATES = 14517  # broad pool
FINAL_CORPUS_SIZE = 3500     # top by citation_count after fetch
```

### Selection methodology
- Broad query captures the RAG/dense-retrieval research universe (~14K candidates)
- Day 2 will fetch metadata + citation count for all candidates
- Final corpus = top 3,500 by citation count
- Rationale: high-citation papers form denser citation subgraphs, improving GraphRAG eval signal

## API key
Submitted form to Semantic Scholar on June 20. Awaiting email.

## Cypher courses
Scheduled for tomorrow.

## Notes
- ...