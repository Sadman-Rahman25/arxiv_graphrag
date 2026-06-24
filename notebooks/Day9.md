## Findings (full dual + vector data, n=14 each)

The original Day 9 partial-data finding (Spearman ρ=−0.866 between
faithfulness and coverage, p=0.026, based on n=7 dual-only judgments)
was OVERTURNED once vector eval completed and dual reached full n=14.

Updated correlations (n=28 pooled, dual+vector full):
- Faithfulness vs Coverage:  ρ=−0.058,  p=0.771  (NO correlation)
- R@10 vs Faithfulness:      ρ=+0.423,  p=0.022  (SIGNIFICANT positive)
- R@10 vs Coverage:          ρ=+0.026,  p=0.896  (no relationship)
- Confidence vs Coverage:    ρ=+0.390,  p=0.040  (significant positive)

Surviving findings:
1. **Retrieval-faithfulness coupling is real.** Better retrieval predicts
   higher faithfulness across retrievers (pooled ρ=+0.423, p=0.022).
   The mechanism: relevant retrieved papers are mechanically easier for
   the generator to cite in ways that match their abstracts.
2. **Confidence calibration is mild but real.** The generator's
   self-reported confidence correlates positively with coverage
   (ρ=+0.390, p=0.040). The model has partial insight into how well
   it answered.

Dead finding:
- **No faithfulness-coverage tradeoff.** Initial n=7 partial-data
  showed ρ=−0.866. Full n=28 shows ρ=−0.058. The original signal was
  a small-sample artifact from the worst-faithfulness questions
  (q01-q04 dual) being judged first.

Aggregate retriever comparison (n=14 each, graph pending):
| Retriever | R@10  | Faith | Cov   |
|-----------|------:|------:|------:|
| dual      | 0.732 | 0.619 | 0.438 |
| vector    | 0.601 | 0.644 | 0.304 |

Dual wins R@10 by +21.8% and coverage by +13.4 points. Vector slightly
ahead on faithfulness by 2.5 points, driven primarily by q11 dual
(10 cites, faith=0.375) — an outlier where dual over-cited. Without
q11, the retrievers are statistically tied on faithfulness.

## Methodological lesson

The n=7 → n=28 inversion is itself a finding. Partial-data analysis
in budget-constrained eval pipelines produces seductive but unreliable
signals. Standard rule: report correlations only at N≥10 per cell,
preferably N≥20.