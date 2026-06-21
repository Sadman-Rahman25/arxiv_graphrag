# save as check_gazetteer_coverage.py
import json
import yaml

with open("gazetteer/methods.yaml", encoding="utf-8") as f:
    methods = yaml.safe_load(f)

# Build a flat list of all aliases (lowercased)
all_aliases = []
for canonical_id, info in methods.items():
    for alias in info.get("aliases", []):
        all_aliases.append((alias.lower(), canonical_id))

# Scan titles
with open("data/raw/papers.jsonl", encoding="utf-8") as f:
    titles = [json.loads(line).get("title", "").lower() for line in f]

# Count matches
from collections import Counter
hits = Counter()
for title in titles:
    for alias, cid in all_aliases:
        if alias in title:
            hits[cid] += 1

print(f"{'Method':<30} {'Title hits':>12}")
print("-" * 44)
for cid, count in hits.most_common(30):
    print(f"{cid:<30} {count:>12}")

print(f"\nTotal unique methods matched in titles: {len(hits)}")
print(f"Total methods in gazetteer:               {len(methods)}")
print(f"Coverage: {100*len(hits)/len(methods):.1f}%")