# Day 6 — Monday, June 22, 2026

## Status: COMPLETE (all 6 gates green)

## Gates
- [x] Context formatter (paper -> LLM prompt block with [Pn] tags)
- [x] Groq Llama-3.3-70B generation with JSON mode + schema validation
- [x] Citation contract (answer/citations/confidence schema)
- [x] Abstention guardrail (no retrieval -> refuse to answer)
- [x] End-to-end CLI src/ask.py
- [x] Tested on 5 diverse queries

## What shipped
- src/format_context.py - paper -> [P1]..[PK] prompt block + paperId lookup
- src/generate_answer.py - Groq wrapper, JSON contract, sha256-keyed cache
- src/ask.py - CLI glue: retrieve -> format -> generate -> resolve -> print

## Citation contract
Strict JSON output: {answer, citations[], confidence: high|medium|low}.
Schema validated with retry-on-failure (max 2 retries). System prompt requires
inline [Pn] citations for every substantive claim.

## Cache design
sha256(model + question + context) -> response, stored as JSONL.
Any retrieval change invalidates the cache automatically. Reruns of same
question hit cache in <50ms.

## Empirical results (5 hand-written queries)
- Q1 (Self-RAG vs Active RAG): high conf, 3 refs. Minor factual stretch
  because the actual Active-RAG (FLARE) paper wasn't in retrieval top-10.
  Documents the retrieval-coverage limit for nuanced comparison queries.
- Q2 (DPR eval datasets): correctly downgraded to low confidence; papers
  did not contain dataset-specific information.
- Q3 (GraphRAG summarization): high conf, 3 refs incl. Microsoft GraphRAG.
- Q4 (hallucination detection): high conf, 9 refs. Comprehensive answer
  enumerating distinct approaches. Showcase result.
- Q5 (legal RAG long docs): medium conf, 4 refs. Correct calibration -
  retrieval was about long-context generally, not legal-specific.

## Findings
- Confidence calibration mostly works. Q2 (low) and Q5 (medium) demonstrate
  appropriate uncertainty. Q1 overclaims at high - a Day 7 eval focus.
- Citation regex needed a fix to handle cluster citations [P1, P3, P5].
  Original regex only matched single-tag brackets [P1].
- Cache hit rate during dev was ~40% (repeated runs of same questions).

## Pending for Day 7
- [ ] Build gold question set (15-25 hand-written Q&A pairs across topics)
- [ ] Retrieval metrics: P@5, MRR, NDCG against gold-relevant papers
- [ ] Answer scoring: faithfulness (claims grounded in cited papers),
      coverage (gold facts present in answer), citation precision
- [ ] Confidence calibration analysis: high/medium/low vs actual quality
- [ ] Baseline comparison: vector-only vs graph-only vs dual retriever