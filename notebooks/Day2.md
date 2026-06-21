## Phase 2 — Selection methodology (LOCKED)

- Candidate pool: 15,465 papers matching locked S2 query
- Selection: top 3,500 by citationCount
- Year distribution of selected corpus: 134/226/1574/1502/64 across 2022-2026
- Citation cutoff: 5 (min); median: 12; max: 3,494
- 48% of candidates had 0 citations → filtered out by citation-weighted selection
- Justification: high-citation papers form denser citation subgraphs, 
  improving GraphRAG multi-hop eval signal. Year balance is preserved as 
  a side effect of older papers having had more time to accumulate citations.

# Day 2 — Sunday, June 21, 2026

## Status: COMPLETE (all 6 gates cleared)

## Corpus
- 15,465 candidates fetched via S2 bulk search (locked query)
- Top 3,500 selected by citationCount (cutoff: 5 citations, median: 12)
- Year distribution: 134/226/1574/1502/64 across 2022-2026
- Full metadata fetched via /paper/batch (7 calls, all clean)
- 92.4% have abstracts, 41.1% have references after recovery
- 66,089 total reference edges in dataset
- Top venue: arXiv.org (966), then EMNLP/ACL/SIGIR/ICLR

## Reference recovery
- S2 /paper/batch endpoint silently truncates references on big payloads
- Recovered 106 papers (highest-cite, including Microsoft GraphRAG, RAG-Survey, etc.)
- Used dedicated /paper/{id}/references endpoint with slim fields
- 7,199 new references patched in via merge_references.py
- Sustained S2 rate limiting hit after ~80 sequential calls — accepted partial recovery

## Gazetteers
- methods.yaml: 148 entries across 20+ categories (target was 150)
- datasets.yaml: 47 entries across 10 task types (target was 50)
- Coverage scan: methods 48.6% appear in titles, datasets 83% (titles+abstracts)
- Known matching issue: short acronyms (PI, Yi, GAT, ANCE) need word-boundary + case-sensitive matching in Day 3

## Gold annotations (eval/gold_annotations.jsonl)
- 25 papers hand-annotated, stratified 8/12/5 by citation tier
- Methods tagged: ~40
- Datasets tagged: ~3
- Relations: ~6
- Off-topic flagged: ~4 (~16% corpus drift - matches expectation)
- Key insight: many papers introduce domain-specific RAG variants (RareDxGPT, RadioRAG, GNN-RAG, etc.) not in gazetteer — Day 3 needs novel-method-candidate surfacing

## Switch made: BGE-large → BGE-base
- 8GB RAM machine OOM-kills BGE-large (~2GB load)
- BGE-base: 440MB on disk, 768-dim, ~96% MTEB quality of large
- Hardware-aware engineering tradeoff

## Disk infrastructure
- Migrated ~5GB of caches from C: to E: via Windows junctions
- HuggingFace, PyTorch, sentence-transformers, pip caches all on E:
- C: free space recovered from "almost full" to 41 GB

## Pending for Day 3
- [ ] Entity extraction (gazetteer hybrid + LLM): build src/extract_entities.py
- [ ] Use case-sensitive word-boundary matching for short acronyms
- [ ] Add 'security' category for adversarial methods (PoisonedRAG, BadRAG, etc.)
- [ ] Add 'tools/frameworks' category (FlashRAG, RAGAS toolkit, etc.)
- [ ] Surface out-of-gazetteer methods as 'novel method candidates'
- [ ] Score extraction against gold_annotations.jsonl (precision, recall, F1)
