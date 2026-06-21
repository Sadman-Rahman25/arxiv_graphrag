"""Figure out WHY 62% of papers are missing references."""
import json
from pathlib import Path
from collections import Counter, defaultdict

with open("data/raw/papers.jsonl", encoding="utf-8") as f:
    papers = [json.loads(line) for line in f]

# Bucket papers by year and ref status
year_ref_status = defaultdict(lambda: {"with_refs": 0, "without_refs": 0})
cite_ref_status = defaultdict(lambda: {"with_refs": 0, "without_refs": 0})

for p in papers:
    year = p.get("year") or "unknown"
    has_refs = bool(p.get("references"))
    cites = p.get("citationCount", 0) or 0
    
    bucket = "with_refs" if has_refs else "without_refs"
    year_ref_status[year][bucket] += 1
    
    # Citation buckets
    if cites >= 100:
        cb = "100+"
    elif cites >= 30:
        cb = "30-99"
    elif cites >= 10:
        cb = "10-29"
    else:
        cb = "5-9"
    cite_ref_status[cb][bucket] += 1

print("=== Reference coverage by YEAR ===")
print(f"{'Year':<8} {'With':>8} {'Without':>8} {'% with refs':>14}")
for year in sorted(year_ref_status.keys(), key=lambda y: (y == "unknown", y)):
    s = year_ref_status[year]
    total = s["with_refs"] + s["without_refs"]
    pct = 100 * s["with_refs"] / total if total else 0
    print(f"{year:<8} {s['with_refs']:>8} {s['without_refs']:>8} {pct:>13.1f}%")

print("\n=== Reference coverage by CITATION BUCKET ===")
print(f"{'Bucket':<10} {'With':>8} {'Without':>8} {'% with refs':>14}")
for bucket in ["100+", "30-99", "10-29", "5-9"]:
    s = cite_ref_status[bucket]
    total = s["with_refs"] + s["without_refs"]
    pct = 100 * s["with_refs"] / total if total else 0
    print(f"{bucket:<10} {s['with_refs']:>8} {s['without_refs']:>8} {pct:>13.1f}%")

# Sample 5 missing-ref papers
print("\n=== Sample papers MISSING references ===")
missing = [p for p in papers if not p.get("references")][:5]
for p in missing:
    arxiv = (p.get("externalIds") or {}).get("ArXiv")
    print(f"  [{p.get('year')}] cites={p.get('citationCount')} arxiv={arxiv} :: {p.get('title', '')[:80]}")