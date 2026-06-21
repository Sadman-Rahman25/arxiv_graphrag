"""Quick check: does the gazetteer matcher agree with gold annotations?"""
import json
from pathlib import Path

# Load gold (key by paperId for fast lookup)
gold = {}
for line in open("eval/gold_annotations.jsonl", encoding="utf-8"):
    rec = json.loads(line)
    gold[rec["paperId"]] = rec

# Load matcher output, filter to gold papers
matches = {}
for line in open("data/extractions/gazetteer_matches.jsonl", encoding="utf-8"):
    rec = json.loads(line)
    if rec["paperId"] in gold:
        matches[rec["paperId"]] = rec

print(f"Comparing {len(matches)} papers against gold annotations\n")
print(f"{'#':<3} {'Gold methods':<35} {'Matcher methods':<35} {'Missed':<20} {'Extra':<20}")
print("-" * 120)

total_gold = 0
total_correct = 0
total_extra = 0

for paper_id, m in matches.items():
    g = gold[paper_id]
    gold_set = set(g["methods"])
    match_set = set(m["methods"])

    correct = gold_set & match_set      # matcher found these and gold has them
    missed = gold_set - match_set       # gold has these, matcher missed
    extra = match_set - gold_set        # matcher found these, not in gold

    total_gold += len(gold_set)
    total_correct += len(correct)
    total_extra += len(extra)

    gold_str = ",".join(sorted(gold_set)) or "(none)"
    match_str = ",".join(sorted(match_set))[:33] or "(none)"
    missed_str = ",".join(sorted(missed)) or "-"
    extra_str = ",".join(sorted(extra))[:18] or "-"

    aid = g["annotation_id"]
    print(f"{aid:<3} {gold_str[:33]:<35} {match_str:<35} {missed_str[:18]:<20} {extra_str:<20}")

# Recall = correct / gold; Precision = correct / matched
if total_gold > 0:
    recall = total_correct / total_gold
    print(f"\nRecall on gold methods: {recall:.2f} ({total_correct}/{total_gold})")
print(f"Extra method matches not in gold: {total_extra} (these may be false positives OR methods you missed in annotation)")


