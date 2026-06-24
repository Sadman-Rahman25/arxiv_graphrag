# Day 8 — Answer generation + LLM-judge eval

## Goal
Build the end-to-end answer pipeline: dual/vector/graph retriever →
context formatter → Groq Llama-3.3-70B generator → judge harness for
faithfulness and coverage. Generate all 42 answers (14 q × 3 retrievers)
and run judge on as many as the daily Groq budget allows.

## Built
- `src/generate_eval_answers.py` — generation harness with per-answer
  cache keyed by (qid, retriever, prompt_version). Supports `--retriever`
  flag; abstains when retrieval returns zero papers.
- `src/eval_answers.py` — LLM-judge harness. Temperature 0,
  Llama-3.3-70B. Per-claim cache keyed by sha256("faith|model|paperId|sentence")
  for faithfulness, sha256("cov|model|fact|answer") for coverage. Stored
  as a single JSONL at `eval/judge_cache.jsonl`.

## Ran
- 42/42 answers generated across dual + vector + graph.
- Graph correctly abstained on q09 (code-RAG; gazetteer has no code-RAG
  bridge — graph SHOULD return nothing here, and it does).
- LLM-judge eval ran in three sessions across two days:
  - Day 8 session 1: q01–q04 dual + q02 vector judged before hitting
    the Groq 100K TPD cap at q05 dual.
  - Day 9 session 2 (after reset): all of dual q01–q14 completed in
    one run (155 cache entries by end).
  - Day 9 session 3 (after reset): all of vector q01–q14 completed in
    one run. Cache-shadow hits with dual (where vector cited overlapping
    paperId+sentence pairs) reduced real token cost.

## Cache-shadow correction
Initial expectation: identical answers across retrievers would share
the same cache key. Actual behavior: the cache key includes paperId
and the specific sentence containing the citation, so shadow hits only
fire when two retrievers cite the same paper in a textually-identical
sentence. This is narrower than expected — meaningful overlap occurred
for high-recall questions where vector and dual retrieved similar top-k
sets and the generator produced similar phrasing.

## Failure modes identified from judge reasoning
1. **Cluster citation dilution** — compound sentences citing 6+ papers
   get each paper judged against the full multi-method claim, producing
   systematic partial verdicts. This is partly a MEASUREMENT ARTIFACT
   (the judge can't easily verify a paper's contribution to a compound
   claim) and partly a generation defect (the prompt allows
   [P1, P3, P5] cluster citations in the first place).
2. **Citation drift** — a [Pn] tag points to a paper whose abstract
   doesn't actually support the local sentence's specific claim
   (e.g., q04 cited LongRAG for a feature belonging to a different
   paper).
3. **Citation parsimony / mechanism gloss** — when retrieval succeeds,
   the generator sometimes paraphrases mechanism specifics into generic
   phrasing without naming the technique. Three concrete examples found:
   q01 dual (Self-RAG retrieved, "reflection tokens" never named),
   q11 dual (10 cites but 7 unsupported because over-citation diluted
   each), q14 vector (perfect R@10 but coverage=0.000 because mDPR,
   language drift, etc. never named).

## Decision: single-judge-model
Considered adding Gemini / other judges to parallelize and break the
budget bottleneck. REJECTED because mixing judge models corrupts the
comparability of aggregate means — different models calibrate the
supported/partial/unsupported boundary differently, so a mean
faithfulness of 0.5 from Llama is not comparable to 0.5 from Gemini.
The right move is to spread the single-model eval across multiple days
as budget resets, optionally adding a small inter-rater agreement
check on a fixed subset after primary eval completes.

## Status at Day 8 close
- dual: 14/14 fully judged (F=0.619, C=0.438)
- vector: 14/14 fully judged (F=0.644, C=0.304)
- graph: 0/13 judged (q09 abstained, not counted) — pending Day 10
- dual_v2: 0/14 generated and judged — pending after graph completes

## Files
- `src/generate_eval_answers.py`
- `src/eval_answers.py`
- `eval/generated_answers.jsonl` (42 entries)
- `eval/judge_cache.jsonl` (227 verdicts at Day 8 close)
- `eval/results/answer_eval_dual_20260624_101816.json`
- `eval/results/answer_eval_vector_20260624_103643.json`