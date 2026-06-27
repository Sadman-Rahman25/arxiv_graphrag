# Day 9 — Analysis infrastructure + final findings

## Goal
Build analysis scripts that require NO API calls (so they run while judge
eval is rate-limited), then apply them to the completed eval data to lock
in the project's defensible findings.

## Built (5 scripts, all API-free)
1. `src/diagnostic_report.py` — joins retrieval R@10 with answer
   faithfulness and coverage into a per-question side-by-side table.
   Reconstructs judge scores from the existing cache by re-deriving the
   same SHA256 keys.
2. `src/correlation_analysis.py` — Spearman rank correlations between
   retrieval quality, answer quality, and generator confidence.
3. `src/failure_cases.py` — markdown reports with full judge reasoning
   per claim and per fact. Flags: `--metric`, `--n`, `--calibration`,
   `--retriever`.
4. `src/run_modified_prompt.py` — generates dual_v2 answers with a
   revised system prompt enforcing atomic claims, verify-before-cite,
   and specific naming. Queued for Day 10.
5. `src/cross_retriever_comparison.py` — the central writeup artifact.
   Aggregates retrieval + answer metrics across all retrievers into one
   markdown + CSV. Handles partial judge data gracefully.

## Eval timeline and budget
The Groq free tier (100K TPD on Llama-3.3-70B) is the binding constraint.
The full judge eval required THREE budget days to complete all 41
judgeable answer cells (q09 graph abstained, correctly):

| Day | Date | Work | Cache size at close |
|-----|------|------|---:|
| 1 | June 24 (morning) | dual q01–q14 judged | 155 |
| 2 | June 24 (evening) | vector q01–q14 judged | 227 |
| 3 | June 27 | graph q01–q08, q10–q14 judged | 349 |

q14 vector hit the daily cap on its final coverage call but the call
had completed; all four coverage verdicts cached cleanly.

## Final aggregate (n=14 per cell, n=41 total)

| Retriever | R@10  | Faithfulness | Coverage | High-conf | Judged |
|-----------|------:|-------------:|---------:|----------:|-------:|
| dual      | 0.732 | 0.619        | 0.438    | 12/14     | 14/14  |
| vector    | 0.601 | 0.644        | 0.304    | 9/14      | 14/14  |
| graph     | 0.258 | 0.654        | 0.240    | 5/14      | 13/14  |

Read top-to-bottom: R@10 and Coverage decrease monotonically, but
Faithfulness slightly increases. This pattern motivates the central
finding about WHERE retrieval quality propagates downstream.

## Final correlations (Spearman ρ, pooled N=41)

**Significant (p<0.05):**

| Pair | ρ | p | Interpretation |
|------|---:|---:|---|
| R@10 vs Coverage | +0.355 | 0.023 | Retrieval quality predicts coverage |
| Confidence vs Coverage | **+0.536** | **<0.001** | Strong, highly significant |

**Not significant:**

| Pair | ρ | p | Interpretation |
|------|---:|---:|---|
| R@10 vs Faithfulness | +0.182 | 0.254 | No relationship at full N |
| Faithfulness vs Coverage | −0.219 | 0.170 | No tradeoff at full N |
| Confidence vs Faithfulness | −0.062 | 0.702 | No relationship |

## Within-retriever correlation worth flagging
Graph R@10 vs Coverage is exceptionally strong at ρ=+0.744, p=0.004
(N=13). Graph's coverage is most dependent on retrieval because graph's
retrieval is most variable (R@10 ranges 0.000 to 1.000 across questions).
When graph hits (e.g. q08 R@10=0.600 → Cov=0.750), it covers well. When
graph misses (e.g. q06 R@10=0.000 → Cov=0.000), coverage collapses
catastrophically.

## The three locked findings

### Finding 1: Retrieval propagates to coverage, not faithfulness
The R@10 → Coverage chain is statistically significant (pooled ρ=+0.355,
p=0.023) AND monotonic across retrievers (dual 0.438 > vector 0.304 >
graph 0.240). The R@10 → Faithfulness chain is NOT significant at full N
(pooled ρ=+0.182, p=0.254). Retrieval improvements travel into the
generator through what gets covered, not through whether citations are
verifiable.

### Finding 2: Dual-pattern retrieval delivers retrieval AND coverage wins
Dual achieves +21.8% R@10 over vector baseline (0.732 vs 0.601) and
+13.4 points coverage (0.438 vs 0.304). The largest single-question win
is q05 (V=0.250, G=0.500, D=1.000) — a pure additive RRF intersection
where vector contributed 1 paper, graph contributed 2, and the fusion
hit perfect recall. Graph alone is weakest on every aggregate except
faithfulness, and that exception is explained by Finding 3.

### Finding 3: Generator confidence is well-calibrated to coverage
Confidence vs Coverage correlates at pooled ρ=+0.536 (p<0.001). When the
generator self-reports "high confidence," coverage really is higher.
When it reports "low" or "abstain," coverage genuinely collapses. This
is the STRONGEST and MOST CERTAIN finding in the project. It survives
across all three retrievers individually and pools to high significance.
Practical implication: the confidence field is a usable production
signal for downstream filtering or human-review routing.

## Dead findings (overturned at full N)

### "Faithfulness-coverage structural tradeoff"
Initial finding at n=7 (partial dual only): ρ=−0.866, p=0.026.
At n=29 (full dual + full vector): ρ=−0.058, p=0.771.
At n=41 (full dual + full vector + full graph): ρ=−0.219, p=0.170.

The −0.866 was a small-sample artifact from the worst-faithfulness
questions (q01–q04 dual) clustering at low coverage. At full N the
pattern is not significant. There is no structural tradeoff.

### "Retrieval quality predicts faithfulness"
Initial finding at n=29: ρ=+0.423, p=0.022 (significant).
At n=41 with graph data added: ρ=+0.182, p=0.254 (NOT significant).

Graph's 13 data points pulled the correlation toward zero. Within-graph
the correlation is precisely zero (ρ=+0.000). This finding does NOT
survive full data.

## Why faithfulness inverts (the citation-density explanation)

Graph's mean faithfulness of 0.654 looks like a generation win until
you look at citation counts. Graph cites fewer papers per answer
(because it retrieves fewer) — and fewer citations means fewer chances
for citation drift. The aggregate "win" is mechanical, not qualitative.

Confirming examples from the per-question table:
- q05 graph: 3 cites → faith=1.000
- q07 graph: 1 cite → faith=1.000
- q11 graph: 2 cites → faith=1.000

Versus dual's over-cite cases:
- q11 dual: 10 cites → faith=0.375
- q13 vector: 10 cites → faith=0.273
- q10 graph: 10 cites → faith=0.050 (retrieval failure cascaded)

The citation-density correlation with faithfulness (lower count → higher
score) is the mechanical explanation for graph's apparent faithfulness
advantage. The actual question is whether dual can recover faithfulness
without losing coverage — this is the Day 10 dual_v2 experiment.

## Per-question patterns worth highlighting

**Discipline benchmark:** q07 across all three retrievers — single-paper
question, 1 citation, faithfulness=1.000 everywhere. Demonstrates that
narrow well-cited answers achieve perfect faithfulness.

**RRF intersection showcase:** q05 — V=0.250, G=0.500, D=1.000. Dual
uniquely hit perfect recall through additive fusion. Coverage and
faithfulness for dual q05 are both above the project mean (cov=0.375,
faith=0.857).

**Citation density penalty:** q11 dual — 10 cites, faith=0.375. Same
question with vector (5 cites, faith=0.750) and graph (2 cites,
faith=1.000) demonstrates that the model's citation density is the
faith driver, not the retrieved paper quality.

**Generator-side failure:** q14 vector — R@10=1.000 (perfect retrieval),
faith=0.786 (reasonable), but coverage=0.000 (catastrophic). The model
wrote about cross-lingual RAG without naming mDPR, language drift, or
cultural sensitivity despite having the papers in context. Demonstrates
that retrieval success is necessary but not sufficient.

**Retrieval failure cascade:** q10 graph — R@10=0.000, generator wrote
10 confident citations anyway, faith=0.050 (1/20 supported). The
clearest case of unwarranted generator confidence on bad retrieval.

**Correct abstention:** q09 graph — abstained because the gazetteer has
no code-RAG method bridge. This is the only abstention in the eval and
demonstrates the retriever knows when it has nothing to offer.

## Methodological lesson
Two findings claimed significance at partial data (p<0.05) and dissolved
at full data. Both directions reversed: the −0.866 weakened toward zero,
the +0.423 weakened to insignificant. Neither was wrong methodology —
both used appropriate Spearman tests with proper p-values — but BOTH
were undermined by N. The standard rule of N≥10 per cell is necessary
but not sufficient when correlation strength is moderate.

The practical takeaway for the project narrative: report findings
ONLY when all retrievers have full data. The cross_retriever_comparison
script's "partial judging shows '—'" design is correct precisely because
of this risk.

## Files at Day 9 close
- `src/diagnostic_report.py`
- `src/correlation_analysis.py`
- `src/failure_cases.py`
- `src/run_modified_prompt.py` (built, not yet executed)
- `src/cross_retriever_comparison.py`
- `eval/judge_cache.jsonl` (349 verdicts)
- `eval/results/answer_eval_dual_20260624_101816.json`
- `eval/results/answer_eval_vector_20260624_103643.json`
- `eval/results/answer_eval_graph_20260625_110930.json`
- `eval/results/diagnostic_20260627_105438.json`
- `eval/results/correlations_20260627_105458.json`
- `eval/results/cross_retriever_comparison_20260627_*.{md,csv}`