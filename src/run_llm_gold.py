"""Run LLM extraction on all 25 gold papers and save aggregated output."""
import sys
import json
import time
from pathlib import Path

# Add src/ to path so we can import extract_llm
sys.path.insert(0, str(Path(__file__).parent))
from extract_llm import extract_for_paper

GOLD_PATH = Path("eval/gold_annotations.jsonl")
PAPERS_PATH = Path("data/raw/papers.jsonl")
GAZETTEER_PATH = Path("data/extractions/gazetteer_matches.jsonl")
OUTPUT_PATH = Path("data/extractions/llm_extractions_gold.jsonl")

# Load gold paper IDs
gold_ids = {json.loads(line)["paperId"] for line in open(GOLD_PATH, encoding="utf-8")}
print(f"Target: {len(gold_ids)} gold papers")

# Load gazetteer matches for those papers
gazetteer = {}
for line in open(GAZETTEER_PATH, encoding="utf-8"):
    rec = json.loads(line)
    if rec["paperId"] in gold_ids:
        gazetteer[rec["paperId"]] = rec

# Run extraction
results = []
n_cached = 0
n_called = 0
n_failed = 0

for line in open(PAPERS_PATH, encoding="utf-8"):
    paper = json.loads(line)
    if paper["paperId"] not in gold_ids:
        continue

    pid = paper["paperId"]
    gaz = gazetteer.get(pid, {"method_aliases": {}, "dataset_aliases": {}})

    # Check if cached before printing
    from extract_llm import cache_path
    was_cached = cache_path(pid).exists()

    title_short = (paper["title"] or "")[:60]
    print(f"  {'(cached)' if was_cached else '(API)':<10} {title_short}")

    result = extract_for_paper(
        paper,
        gaz.get("method_aliases", {}),
        gaz.get("dataset_aliases", {}),
        use_cache=True,
    )

    if result is None:
        n_failed += 1
        print("    FAILED")
        continue

    if was_cached:
        n_cached += 1
    else:
        n_called += 1

    result["paperId"] = pid
    result["title"] = paper["title"]
    results.append(result)

    if not was_cached:
        time.sleep(1.5)  # rate limit pacing for new API calls

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    for r in results:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"\nResults: {n_cached} cached + {n_called} new API calls + {n_failed} failed")
print(f"Saved {len(results)} extractions to {OUTPUT_PATH}")


