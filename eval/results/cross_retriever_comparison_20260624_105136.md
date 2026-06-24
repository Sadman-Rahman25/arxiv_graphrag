# Cross-Retriever Comparison Report

Generated: 2026-06-24T10:51:36
Retrieval eval source: `retrieval_eval_20260622_220716.json`
Retrievers compared: dual, vector, graph, dual_v2
Judge model: `llama-3.3-70b-versatile`
Judge cache: `eval/judge_cache.jsonl` (227 entries)
Facts file: `D:\arxiv-graphrag\eval\expected_facts.jsonl`

## Aggregate metrics

| Retriever | n | answered | abstained | judged | R@5 | R@10 | MRR | Faithfulness | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dual | 14 | 14 | 0 | 14 | 0.593 | 0.732 | 0.717 | 0.619 | 0.438 |
| vector | 14 | 14 | 0 | 14 | 0.476 | 0.601 | 0.571 | 0.644 | 0.304 |
| graph | 14 | 13 | 0 | 0 | 0.244 | 0.258 | 0.310 | — | — |
| dual_v2 | 14 | 0 | 0 | 0 | 0.593 | 0.732 | 0.717 | — | — |

**Judge coverage:** 28/41 answers fully judged (68.3%).

*An answer counts as 'judged' only when every claim AND every expected fact has a cache entry. Partials show '—' and are excluded from aggregate means.*

## Pairwise comparisons

### Pairwise wins on Recall@10

| A | B | n | A wins | B wins | ties |
|---|---|---:|---:|---:|---:|
| dual | vector | 14 | 4 | 1 | 9 |
| dual | graph | 14 | 10 | 0 | 4 |
| dual | dual_v2 | 14 | 0 | 0 | 14 |
| vector | graph | 14 | 8 | 3 | 3 |
| vector | dual_v2 | 14 | 1 | 4 | 9 |
| graph | dual_v2 | 14 | 0 | 10 | 4 |

### Pairwise wins on Faithfulness

| A | B | n | A wins | B wins | ties |
|---|---|---:|---:|---:|---:|
| dual | vector | 14 | 3 | 5 | 6 |

### Pairwise wins on Coverage

| A | B | n | A wins | B wins | ties |
|---|---|---:|---:|---:|---:|
| dual | vector | 14 | 6 | 0 | 8 |

## Per-question grid

| qid | regime | dual R@10 | dual faith | dual cov | vector R@10 | vector faith | vector cov | graph R@10 | graph faith | graph cov | dual_v2 R@10 | dual_v2 faith | dual_v2 cov |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| q01 | single-method-noisy | 0.600 | 0.500 | 0.250 | 0.000 | 0.667 | 0.125 | 0.600 | — | — | 0.600 | — | — |
| q02 | single-method-noisy | 0.600 | 0.333 | 0.750 | 0.600 | 0.333 | 0.750 | 0.000 | — | — | 0.600 | — | — |
| q03 | specific-named-entity | 0.750 | 0.500 | 0.250 | 1.000 | 0.700 | 0.250 | 0.250 | — | — | 0.750 | — | — |
| q04 | vector-only-no-bridges | 0.400 | 0.571 | 0.250 | 0.400 | 0.571 | 0.250 | 0.000 | — | — | 0.400 | — | — |
| q05 | multi-method-precise | 1.000 | 0.857 | 0.375 | 0.250 | 0.500 | 0.375 | 0.500 | — | — | 1.000 | — | — |
| q06 | single-method-specific | 0.500 | 0.750 | 0.375 | 0.500 | 0.750 | 0.375 | 0.000 | — | — | 0.500 | — | — |
| q07 | single-paper-focused | 1.000 | 1.000 | 0.500 | 1.000 | 1.000 | 0.500 | 0.000 | — | — | 1.000 | — | — |
| q08 | multi-method | 0.600 | 0.900 | 0.750 | 0.200 | 0.875 | 0.375 | 0.600 | — | — | 0.600 | — | — |
| q09 | multi-method | 0.800 | 0.500 | 0.250 | 0.800 | 0.500 | 0.250 | 0.000 | — | — | 0.800 | — | — |
| q10 | vector-only-no-bridges | 1.000 | 0.938 | 0.250 | 1.000 | 0.938 | 0.250 | 0.000 | — | — | 1.000 | — | — |
| q11 | single-method-specific | 1.000 | 0.375 | 0.750 | 1.000 | 0.750 | 0.250 | 1.000 | — | — | 1.000 | — | — |
| q12 | multi-method | 0.000 | 0.333 | 0.375 | 0.000 | 0.375 | 0.250 | 0.000 | — | — | 0.000 | — | — |
| q13 | multi-method | 1.000 | 0.500 | 0.750 | 0.667 | 0.273 | 0.250 | 0.667 | — | — | 1.000 | — | — |
| q14 | vector-only-no-bridges | 1.000 | 0.611 | 0.250 | 1.000 | 0.786 | 0.000 | 0.000 | — | — | 1.000 | — | — |

## Headline finding

- **dual** has the best mean Recall@10 at 0.732, a +21.8% change vs the vector baseline (0.601).
- **vector** has the best mean faithfulness at 0.644 (across 14 fully-judged answers).
- **dual** has the best mean coverage at 0.438.
