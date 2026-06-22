# Day 7 — Monday, June 22, 2026

## Status: COMPLETE (all 6 gates green)

## Gates
- [x] Gold question set with 14 hand-annotated questions across 6 regimes
- [x] Interactive annotation helper (build_gold.py)
- [x] Evaluation harness (eval_retrieval.py) with Recall@K and MRR
- [x] First eval run on 8-question starter
- [x] Expanded to 14 questions
- [x] Per-query analysis + writeup

## Gold question set
14 questions, 6 regimes:
- single-method-noisy (2):     q01, q02
- single-method-specific (2):  q06, q11
- specific-named-entity (1):   q03
- single-paper-focused (1):    q07
- vector-only-no-bridges (3):  q04, q10, q14
- multi-method (5):            q05, q08, q09, q12, q13

Methodology: incomplete-relevance judgments. Mark "must-find" papers
(3-7 per question typically), let unjudged-but-relevant papers stay
unmarked. Primary metric: Recall@K. Precision@K would penalize for
surfacing unjudged-relevant papers, which is unfair under incomplete
gold (standard TREC/BEIR practice).

## Aggregate retrieval metrics (14 questions, k=10)

| Retriever | Recall@5 | Recall@10 | MRR   |
|-----------|---------:|----------:|------:|
| vector    |   0.476  |   0.601   | 0.571 |
| graph     |   0.244  |   0.258   | 0.310 |
| dual      | **0.593**| **0.732** |**0.717**|

Dual improves over vector baseline by:
  +24.6% Recall@5, +21.8% Recall@10, +25.6% MRR.

Dual beats graph by 2-3x on every metric (expected: graph alone is
brittle to gazetteer coverage). The fact that graph is weaker alone but
strengthens dual via RRF intersection is the central finding.

## Per-query results

| ID  | Regime                     | V R@10 | G R@10 | D R@10 | Winner  |
|-----|----------------------------|-------:|-------:|-------:|---------|
| q01 | single-method-noisy        | 0.000  | 0.600  | 0.600  | G/D     |
| q02 | single-method-noisy        | 0.600  | 0.000  | 0.600  | V/D     |
| q03 | specific-named-entity      | 1.000  | 0.250  | 0.750  | V       |
| q04 | vector-only-no-bridges     | 0.400  | 0.000  | 0.400  | V/D     |
| q05 | multi-method-precise       | 0.250  | 0.500  | 1.000  | D       |
| q06 | single-method-specific     | 0.500  | 0.000  | 0.500  | V/D     |
| q07 | single-paper-focused       | 1.000  | 0.000  | 1.000  | V/D     |
| q08 | multi-method               | 0.200  | 0.600  | 0.600  | G/D     |
| q09 | multi-method               | 0.800  | 0.000  | 0.800  | V/D     |
| q10 | vector-only-no-bridges     | 1.000  | 0.000  | 1.000  | V/D     |
| q11 | single-method-specific     | 1.000  | 1.000  | 1.000  | V/G/D   |
| q12 | multi-method               | 0.000  | 0.000  | 0.000  | tie-zero|
| q13 | multi-method               | 0.667  | 0.667  | 1.000  | D       |
| q14 | vector-only-no-bridges     | 1.000  | 0.000  | 1.000  | V/D     |

Dual is the outright winner or tied for first on 13 of 14 queries.
Only regression: q03 (dual=0.750 vs vector=1.000), documented below.

## Showcase wins (RRF intersection effect)

- q05 (dpr + hard_negative_mining): V=0.250, G=0.500, D=1.000.
  Pure additive win - dual unioned 1 paper from vector + 2 from graph
  to hit perfect recall at 4/4. Cleanest demonstration of
  complementarity.

- q13 (HyDE vs Query2Doc): V=0.667, G=0.667, D=1.000.
  Both retrievers found 2/3 gold papers, but DIFFERENT subsets.
  RRF surfaced the union.

- q01 (Self-RAG): V=0.000, G=0.600.
  Self-RAG itself was at v#20 (BGE didn't lexically match "self-correcting"
  to "self-reflective"). Graph saved the complete vector failure via
  the self_rag method bridge.

## The one regression: q03 (Microsoft GraphRAG)

V=1.000, G=0.250, D=0.750.

Vector perfectly retrieved all 4 gold papers about MS GraphRAG and
related corpus-level summarization. Graph's secondary sort by citation
count surfaced different (also-graphrag-mentioning) papers, which RRF
pulled into the dual top-10 displacing one vector-ranked gold paper.

Acceptable trade-off given the gains elsewhere. Documented as a
limitation of citation-count secondary sort in graph retrieval.

## Adaptive RRF design (final, validated)

graph_weight depends on entity match count from gazetteer:
  0 entities -> 0.0  (pure vector fallback)
  1 entity   -> 0.7  (low trust)
  2+ entities -> 1.5 (high trust per Day 4 finding)

## Rejected polish: IDF weighting

Hypothesized that method specificity (rarity) should modulate graph
trust: rare methods (graphrag at 90 mentions) should boost graph more
than common methods (rag at 3,078 mentions). Tested with:

  weight = clamp(0.5, 1.5, 0.5 + log(3500/count)/3.0)

Eval showed this BACKFIRED on q03 (Recall@10 dropped 0.750 -> 0.500).
Root cause: graph's secondary sort is by citation count, not relevance.
Boosting graph weight for rare-method matches surfaced top-cited papers
mentioning the rare method, not necessarily query-relevant ones.

Finding: method rarity does not predict graph result quality. The
single-vs-multi entity boundary captures the real reliability signal:
multi-entity matches narrow the candidate set enough that citation-sort
is reasonable; single-entity matches don't, regardless of method
frequency. Reverted to v2 logic.

## Corpus coverage limitations (surfaced by eval)

q12 (cross-encoder rerankers + bi-encoder dense retrievers): all three
retrievers scored 0.000. Despite "reranker" being a methodologically
important topic in RAG/IR research, the corpus's reranker coverage is
weak - candidate top-20 contained mostly tangential or wrong-domain
papers. The system honestly fails rather than confabulating.

This is a corpus limitation, not a retrieval limitation. Worth a
paragraph in the writeup: the gold set surfaces real gaps in research
coverage, which would inform Day 8 answer-eval design (low confidence
should correlate with these gaps).

## Files added today
- eval/gold_questions.jsonl (14 questions, hand-annotated)
- eval/results/retrieval_eval_*.json (multiple eval runs preserved)
- src/build_gold.py (interactive annotation tool)
- src/eval_retrieval.py (Recall@K + MRR harness)
- src/retrieve_dual.py (reverted to v2 after IDF polish failed)

## Pending for Day 8
- [ ] Answer-level evaluation: faithfulness via LLM judge
- [ ] Citation precision: do [Pn] citations support the claim
- [ ] Coverage: do answers contain the key facts from gold papers
- [ ] Confidence calibration: high/medium/low predictions vs measured quality
- [ ] Compare answer quality across vector vs graph vs dual retrievals