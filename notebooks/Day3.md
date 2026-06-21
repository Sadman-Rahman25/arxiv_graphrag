# Day 3 - Sunday, June 21 / Monday, June 22, 2026

## Status: PARTIALLY COMPLETE (validated, partial coverage)

## What shipped
- Gazetteer matcher with word-boundary + case-sensitive regex
  - Methods: 92.7% coverage (3,245 / 3,500 papers)
  - Datasets: 6.6% coverage (datasets rarely in abstracts)
- LLM extraction pipeline with Llama-3.3-70B + Groq
  - Validated on 25 gold papers: F1 = 0.788 (methods), 88% scope accuracy
  - 74 papers fully extracted with LLM (25 gold via 70B + 49 corpus via 8B)
  - Cache + retry + JSON-schema-strict design

## Gazetteer additions (Stage 1)
- Added adversarial category (PoisonedRAG, BadRAG, TrojRAG, AgentPoison, prompt_injection)
- Added framework category (FlashRAG, Haystack, Pyserini, RAGFlow)
- Total: 157 methods, 22 categories

## Engineering decisions
- Word-boundary + case-sensitive matching fixed Day 2 false positives (Yi, GAT, ANCE)
- Three-rule alias matching: phrase / has-upper / all-lower
- LLM prompt iteration fixed: alias-aware (LLM knows WebQSP = webquestions),
  conservative on novel methods (no descriptive phrases), constrained relations
- Switched to 8B model after 70B TPD exhaustion (free tier)

## Constraints encountered
- Groq free-tier TPD: 100K on 70B, ~500K on 8B
- Daily budget supports ~50-200 papers per model
- Full corpus extraction requires multiple days; cache makes it incremental

## Carry-over to Day 4 and beyond
- [ ] Run run_llm_full.py daily until corpus is ~80% extracted
- [ ] LLM extractions accumulate in cache - no work lost
- [ ] Day 4 graph build uses gazetteer matches as primary source,
      LLM extractions as enrichment where available

## Novel methods surfaced (for gazetteer growth)
- DPA-RAG, GNN-RAG, COBRA, CL-DRD, iRAG, RareDxGPT, RTLFixer,
  RadioRAG, mAggretriever, BRAD, MOYA, BeamFusion, Chain of Explorations
- Pattern: domain-specific RAG variants dominate (medical, finance, robotics)

## Files created today
- src/match_gazetteer.py
- src/smoke_test_gazetteer.py
- src/extract_llm.py
- src/run_llm_gold.py
- src/score_extraction.py
- src/run_llm_full.py
- data/extractions/gazetteer_matches.jsonl (3,500 records)
- data/extractions/llm_extractions_gold.jsonl (25 records)
- data/extractions/llm_extractions_full.jsonl (74 records, incremental)
- data/extractions/llm_cache/ (74 cached responses)
- eval/extraction_scores - documented inline in Day3.md
