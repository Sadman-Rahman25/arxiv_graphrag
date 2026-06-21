"""Pick 25 papers for hand-annotation, stratified by citation count."""
import json
import random
from pathlib import Path

INPUT = Path("data/raw/papers.jsonl")
OUTPUT = Path("eval/annotation_targets.jsonl")
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

random.seed(42)  # reproducible selection

papers = [json.loads(line) for line in open(INPUT, encoding="utf-8")]

# Only annotate papers WITH abstracts (we need text to read)
papers = [p for p in papers if p.get("abstract")]

# Sort by citation count descending
papers.sort(key=lambda p: p.get("citationCount", 0), reverse=True)

# Stratify
high = papers[:200]           # top 200 by citation
mid = papers[200:1500]        # middle band
low = papers[1500:]           # rest

selected = (
    random.sample(high, 8) +
    random.sample(mid, 12) +
    random.sample(low, 5)
)

# Save with just the fields we need for annotation
with open(OUTPUT, "w", encoding="utf-8") as f:
    for i, p in enumerate(selected, 1):
        rec = {
            "annotation_id": i,
            "paperId": p["paperId"],
            "arxiv_id": (p.get("externalIds") or {}).get("ArXiv"),
            "year": p.get("year"),
            "citationCount": p.get("citationCount"),
            "title": p.get("title"),
            "abstract": p.get("abstract"),
        }
        f.write(json.dumps(rec) + "\n")

print(f"Selected {len(selected)} papers for annotation")
print(f"Saved to {OUTPUT}")
print(f"\nDistribution:")
print(f"  High-cite (8): citations range {selected[0]['citationCount']} - {selected[7]['citationCount']}")
print(f"  Mid-cite (12): citations range {selected[8]['citationCount']} - {selected[19]['citationCount']}")
print(f"  Low-cite (5):  citations range {selected[20]['citationCount']} - {selected[24]['citationCount']}")
