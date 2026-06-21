"""Score LLM extractions against hand-annotated gold."""
import json
from pathlib import Path

GOLD_PATH = Path("eval/gold_annotations.jsonl")
LLM_PATH = Path("data/extractions/llm_extractions_gold.jsonl")

# Load both
gold = {json.loads(line)["paperId"]: json.loads(line) for line in open(GOLD_PATH, encoding="utf-8")}
llm = {json.loads(line)["paperId"]: json.loads(line) for line in open(LLM_PATH, encoding="utf-8")}

# Per-paper aggregates
method_tp = method_fp = method_fn = 0
dataset_tp = dataset_fp = dataset_fn = 0
scope_correct = 0
scope_total = 0
novel_methods_all = []
novel_datasets_all = []

# Per-paper diagnostic
diff_rows = []

for paper_id, g in gold.items():
    if paper_id not in llm:
        continue
    l = llm[paper_id]

    # Methods: gold list vs llm confirmed
    gold_methods = set(g["methods"])
    llm_methods = set(l.get("methods_confirmed", []))

    method_tp += len(gold_methods & llm_methods)
    method_fp += len(llm_methods - gold_methods)
    method_fn += len(gold_methods - llm_methods)

    # Datasets
    gold_datasets = set(g["datasets"])
    llm_datasets = set(l.get("datasets_confirmed", []))

    dataset_tp += len(gold_datasets & llm_datasets)
    dataset_fp += len(llm_datasets - gold_datasets)
    dataset_fn += len(gold_datasets - llm_datasets)

    # Scope: gold infers off-topic from methods=[] AND notes mention off-topic
    gold_offtopic = (not g["methods"]) and ("OFF-TOPIC" in g.get("notes", "").upper() or "off-topic" in g.get("notes", "").lower())
    llm_offtopic = not l.get("in_scope", True)
    if gold_offtopic == llm_offtopic:
        scope_correct += 1
    scope_total += 1

    novel_methods_all.extend(l.get("methods_novel", []))
    novel_datasets_all.extend(l.get("datasets_novel", []))

    # Diagnostic row
    aid = g["annotation_id"]
    title = (g["title"] or "")[:40]
    diff_rows.append({
        "id": aid,
        "title": title,
        "gold_m": gold_methods,
        "llm_m": llm_methods,
        "miss_m": gold_methods - llm_methods,
        "extra_m": llm_methods - gold_methods,
    })

# Print per-paper table
diff_rows.sort(key=lambda r: r["id"])
print(f"{'#':<3} {'Title':<42} {'Gold M':<25} {'LLM M':<25} {'Miss':<15} {'Extra':<15}")
print("-" * 130)
for r in diff_rows:
    g_str = ",".join(sorted(r["gold_m"]))[:23] or "-"
    l_str = ",".join(sorted(r["llm_m"]))[:23] or "-"
    mi_str = ",".join(sorted(r["miss_m"]))[:13] or "-"
    ex_str = ",".join(sorted(r["extra_m"]))[:13] or "-"
    print(f"{r['id']:<3} {r['title']:<42} {g_str:<25} {l_str:<25} {mi_str:<15} {ex_str:<15}")


def prf(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) > 0 else 0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0
    f = 2 * p * r / (p + r) if (p + r) > 0 else 0
    return p, r, f


m_p, m_r, m_f = prf(method_tp, method_fp, method_fn)
d_p, d_r, d_f = prf(dataset_tp, dataset_fp, dataset_fn)

print(f"\n=== METHODS scoring ===")
print(f"  TP={method_tp}, FP={method_fp}, FN={method_fn}")
print(f"  Precision: {m_p:.3f}")
print(f"  Recall:    {m_r:.3f}")
print(f"  F1:        {m_f:.3f}")

print(f"\n=== DATASETS scoring ===")
print(f"  TP={dataset_tp}, FP={dataset_fp}, FN={dataset_fn}")
print(f"  Precision: {d_p:.3f}")
print(f"  Recall:    {d_r:.3f}")
print(f"  F1:        {d_f:.3f}")

print(f"\n=== SCOPE detection ===")
print(f"  Correct: {scope_correct}/{scope_total} ({100*scope_correct/scope_total:.1f}%)")

print(f"\n=== NOVEL methods surfaced (not in gold) ===")
print(f"  Total: {len(novel_methods_all)}, Unique: {len(set(novel_methods_all))}")
for nm in sorted(set(novel_methods_all)):
    print(f"    {nm}")

print(f"\n=== NOVEL datasets surfaced (not in gold) ===")
print(f"  Total: {len(novel_datasets_all)}, Unique: {len(set(novel_datasets_all))}")
for nd in sorted(set(novel_datasets_all)):
    print(f"    {nd}")


