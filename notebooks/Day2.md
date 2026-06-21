## Phase 2 — Selection methodology (LOCKED)

- Candidate pool: 15,465 papers matching locked S2 query
- Selection: top 3,500 by citationCount
- Year distribution of selected corpus: 134/226/1574/1502/64 across 2022-2026
- Citation cutoff: 5 (min); median: 12; max: 3,494
- 48% of candidates had 0 citations → filtered out by citation-weighted selection
- Justification: high-citation papers form denser citation subgraphs, 
  improving GraphRAG multi-hop eval signal. Year balance is preserved as 
  a side effect of older papers having had more time to accumulate citations.