import json
from pathlib import Path

INPUT = Path("eval/annotation_targets.jsonl")
recs = [json.loads(line) for line in open(INPUT, encoding="utf-8")]

for r in recs[20:25]:
    print(f"--- #{r['annotation_id']} | cites={r['citationCount']} | year={r['year']} ---")
    print(f"Title: {r['title']}")
    print(f"arXiv: {r['arxiv_id']}")
    abstract = (r['abstract'] or '')[:700]
    print(f"Abstract: {abstract}")
    print()
