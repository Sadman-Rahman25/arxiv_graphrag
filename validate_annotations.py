import json

recs = [json.loads(line) for line in open("eval/gold_annotations.jsonl", encoding="utf-8")]

print(f"Annotations: {len(recs)}")
print(f"Total methods tagged: {sum(len(r['methods']) for r in recs)}")
print(f"Total datasets tagged: {sum(len(r['datasets']) for r in recs)}")
print(f"Total relations: {sum(len(r['relations']) for r in recs)}")
print(f"Off-topic flagged: {sum(1 for r in recs if not r['methods'])}/25")
