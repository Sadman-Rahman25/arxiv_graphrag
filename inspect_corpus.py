"""Quick sanity check on data/raw/papers.jsonl."""
import json
from pathlib import Path
from collections import Counter

PATH = Path("data/raw/papers.jsonl")

papers = []
with open(PATH, encoding="utf-8") as f:
    for line in f:
        papers.append(json.loads(line))

print(f"Total papers: {len(papers)}")

# First paper detail
p = papers[0]
print(f"\nFirst paper:")
print(f"  Title:        {p.get('title')}")
print(f"  Year:         {p.get('year')}")
print(f"  Citations:    {p.get('citationCount')}")
print(f"  Authors:      {len(p.get('authors') or [])}")
print(f"  References:   {len(p.get('references') or [])}")
print(f"  Has abstract: {bool(p.get('abstract'))}")
print(f"  arXiv ID:     {(p.get('externalIds') or {}).get('ArXiv')}")

# Population-level checks
n_with_abstract = sum(1 for p in papers if p.get("abstract"))
n_with_refs = sum(1 for p in papers if p.get("references"))
ref_counts = [len(p.get("references") or []) for p in papers]
abstract_lens = [len(p.get("abstract") or "") for p in papers if p.get("abstract")]

print(f"\nCorpus-level stats:")
print(f"  Papers with abstract:   {n_with_abstract:,} / {len(papers):,} ({100*n_with_abstract/len(papers):.1f}%)")
print(f"  Papers with references: {n_with_refs:,} / {len(papers):,} ({100*n_with_refs/len(papers):.1f}%)")
print(f"  Avg abstract length:    {sum(abstract_lens)/len(abstract_lens):.0f} chars")
print(f"  Avg refs per paper:     {sum(ref_counts)/len(ref_counts):.1f}")
print(f"  Total references:       {sum(ref_counts):,}")

# Venue distribution (top 10)
venues = Counter(p.get("venue") for p in papers if p.get("venue"))
print(f"\nTop 10 venues:")
for v, count in venues.most_common(10):
    print(f"  {count:>4}  {v[:70]}")