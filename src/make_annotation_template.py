"""Generate annotation template skeleton."""
import json
from pathlib import Path

INPUT = Path("eval/annotation_targets.jsonl")
OUTPUT = Path("eval/gold_annotations_template.jsonl")

with open(INPUT, encoding="utf-8") as f, open(OUTPUT, "w", encoding="utf-8") as out:
    for line in f:
        target = json.loads(line)
        skeleton = {
            "annotation_id": target["annotation_id"],
            "paperId": target["paperId"],
            "title": target["title"],
            # ---- YOU FILL THESE IN ----
            "methods": [],         # list of canonical method IDs from methods.yaml
            "datasets": [],        # list of canonical dataset IDs from datasets.yaml
            "relations": [],       # list of {"head": method_id, "type": "INTRODUCES|USES|EVALUATED_ON", "tail": id}
            "notes": "",           # any free-form notes (out-of-gazetteer methods, edge cases)
        }
        out.write(json.dumps(skeleton) + "\n")

print(f"Template at {OUTPUT}")
print(f"Now read each paper's abstract from annotation_targets.jsonl and fill in the template.")
print(f"When done, rename to gold_annotations.jsonl.")
