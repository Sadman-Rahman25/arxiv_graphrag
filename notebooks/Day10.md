# Day 10 — dual_v2 prompt experiment

## Refined hypothesis (post-Day 9 data)

The Day 9 analysis identified that dual's 2.5-point faithfulness deficit
vs vector is driven by CITATION DENSITY, not by retrieval quality. Dual
retrieves more relevant papers (R@10=0.732 vs vector 0.601), the
generator cites more of them, and citation drift accumulates marginally
with each additional citation.

The driving outlier is q11 dual (10 citations, faithfulness 0.375).
Without q11, dual and vector are statistically tied on faithfulness
(0.638 vs 0.636).

**Hypothesis:** A prompt that enforces atomic claims (one citation per
sentence), verify-before-cite (each [Pn] tag must support the local
sentence), and specific naming (exact technique names from abstracts)
should reduce dual's citation density while preserving its coverage and
R@10 advantages — closing the faithfulness gap without losing the
retrieval gains.

## Pre-registered predictions

I'm writing these BEFORE running dual_v2 so the experiment is honest.

1. **dual_v2 mean cites < dual mean cites.** Specifically, q11 dual_v2
   should drop from 10 cites toward 4-6.

2. **dual_v2 faithfulness > dual faithfulness.** Target: ≥0.640
   (matching vector). Specifically, q11 dual_v2 faithfulness should
   improve from 0.375 toward 0.700+.

3. **dual_v2 coverage stays within 0.05 of dual coverage.** Target:
   0.39–0.49 (dual baseline is 0.438). If coverage drops below 0.388,
   the prompt is over-suppressing and the experiment failed.

4. **dual_v2 R@10 = dual R@10 = 0.732.** Identical retrieval — only
   generation differs.

## Success criteria

The experiment SUCCEEDS if all four predictions hold. This would
demonstrate:
- The citation-density story is causal, not just correlational
- Prompt-level interventions can address generation-side failures
  identified in the analysis
- Dual + dual_v2 dominates vector on ALL three metrics simultaneously

## Failure modes and what they would tell us

**Failure mode A: cites drop, faith stays the same.** Citation density
isn't actually driving the faith gap. Something else (retrieval noise,
generator confusion under tighter constraints) is responsible.

**Failure mode B: cites drop, coverage drops too.** The model needs
high citation density to cover the question. The tradeoff is real but
inverse to what Day 9 originally claimed — fewer cites = less coverage.

**Failure mode C: faith improves on judged claims, but total claim
count drops so much that aggregate "covered facts" falls.** Same
underlying issue as B; would manifest as fewer present-verdicts even
if per-claim verdicts improve.

**Failure mode D: prompt confuses the model (low confidence answers,
generic phrasing).** The atomic-claim rule may be too restrictive for
multi-method questions where compound claims are natural.

Any of these would be ALSO INTERESTING findings — they sharpen our
understanding of how retrieval, citation, and coverage interact.

## Execution plan

### Step 1: Generate dual_v2 answers
```powershell
python src\run_modified_prompt.py --all
```
- Token cost: ~3K per question × 14 = ~42K tokens
- Output: 14 new entries in `eval/generated_answers.jsonl` with
  retriever="dual_v2"

### Step 2: Judge dual_v2 answers
```powershell
python src\eval_answers.py --retriever dual_v2
```
- Token cost: estimated 50-70K tokens (faith + coverage)
- Cache-shadow hits: low (dual_v2 uses different sentence structure
  than dual, so paperId+sentence keys won't match)
- May span 1-2 budget days

### Step 3: Regenerate analysis
```powershell
python src\diagnostic_report.py
python src\correlation_analysis.py
python src\cross_retriever_comparison.py
```

### Step 4: Compare against pre-registered predictions
Document outcome explicitly in this file: which predictions held,
which failed, what the data tells us either way.

## Budget arithmetic

Today's graph eval consumed an unknown but large fraction of the
100K daily budget. Generation (Step 1) costs ~42K. If today's budget
is exhausted, Step 1 waits until tomorrow. The script is resumable.

Worst case timeline: Step 1 tomorrow (~42K), Step 2 the day after
(~50-70K). Step 3 has no token cost. Two budget days to complete the
experiment.

## Why this matters for the writeup

The three Day 9 findings are correlational. The dual_v2 experiment is
quasi-experimental — it manipulates ONE variable (the prompt) while
holding retrieval constant. If predictions 1-4 hold, the writeup gains:

- A causal claim (prompt-level intervention reduces citation density)
- A demonstration of how the analysis findings translated into a
  targeted intervention
- A complete pipeline story: retrieval (dual) → analysis (citation
  density penalty) → intervention (dual_v2) → measurement

This is the narrative arc that converts a benchmarking project into a
diagnostic study.