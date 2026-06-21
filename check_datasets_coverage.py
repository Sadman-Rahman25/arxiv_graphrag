# save as check_datasets_coverage.py
import json
import yaml

with open("gazetteer/datasets.yaml", encoding="utf-8") as f:
    datasets = yaml.safe_load(f)

all_aliases = []
for canonical_id, info in datasets.items():
    for alias in info.get("aliases", []):
        all_aliases.append((alias.lower(), canonical_id))

with open("data/raw/papers.jsonl", encoding="utf-8") as f:
    # Scan both titles AND abstracts for datasets (datasets are rarely in titles)
    texts = []
    for line in f:
        p = json.loads(line)
        text = (p.get("title", "") + " " + (p.get("abstract") or "")).lower()
        texts.append(text)

from collections import Counter
hits = Counter()
for text in texts:
    for alias, cid in all_aliases:
        if alias in text:
            hits[cid] += 1

print(f"{'Dataset':<30} {'Hits':>10}")
print("-" * 42)
for cid, count in hits.most_common(30):
    print(f"{cid:<30} {count:>10}")

print(f"\nDatasets matched: {len(hits)} / {len(datasets)}  ({100*len(hits)/len(datasets):.1f}%)")