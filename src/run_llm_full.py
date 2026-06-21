"""Run LLM extraction on the full 3,500-paper corpus.

Uses cache aggressively. Safe to interrupt with Ctrl+C and resume later.
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from extract_llm import extract_for_paper, cache_path

PAPERS_PATH = Path("data/raw/papers.jsonl")
GAZETTEER_PATH = Path("data/extractions/gazetteer_matches.jsonl")
OUTPUT_PATH = Path("data/extractions/llm_extractions_full.jsonl")

# Load gazetteer matches
print("Loading gazetteer matches...")
gazetteer = {}
for line in open(GAZETTEER_PATH, encoding="utf-8"):
    rec = json.loads(line)
    gazetteer[rec["paperId"]] = rec
print(f"Loaded {len(gazetteer)} gazetteer match records")

# Count cached vs pending for time estimate
print("Counting cached vs pending...")
total = 0
cached_count = 0
for line in open(PAPERS_PATH, encoding="utf-8"):
    paper = json.loads(line)
    total += 1
    if cache_path(paper["paperId"]).exists():
        cached_count += 1

pending = total - cached_count
print(f"Total papers: {total}")
print(f"Already cached: {cached_count}")
print(f"Pending API calls: {pending}")
print(f"Estimated time: ~{pending * 3.0 / 60:.0f} minutes (~{pending * 3.0 / 3600:.1f} hours)")
print()

response = input("Begin? (y/n): ")
if response.lower() != "y":
    print("Aborted.")
    sys.exit(0)

# Run extraction
n_processed = 0
n_failed = 0
n_api_calls = 0
start = time.time()

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
try:
    with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
        for line in open(PAPERS_PATH, encoding="utf-8"):
            paper = json.loads(line)
            pid = paper["paperId"]
            was_cached = cache_path(pid).exists()

            gaz = gazetteer.get(pid, {"method_aliases": {}, "dataset_aliases": {}})
            result = extract_for_paper(
                paper,
                gaz.get("method_aliases", {}),
                gaz.get("dataset_aliases", {}),
                use_cache=True,
            )

            if result is None:
                n_failed += 1
                n_processed += 1
                continue

            record = {
                "paperId": pid,
                "title": paper["title"],
                **result,
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()

            n_processed += 1
            if not was_cached:
                n_api_calls += 1
                time.sleep(1.5)  # pacing only for fresh API calls

            if n_processed % 50 == 0:
                elapsed = time.time() - start
                rate = n_processed / elapsed if elapsed > 0 else 0
                remaining = (total - n_processed) / rate if rate > 0 else 0
                pct = 100 * n_processed / total
                print(f"  {n_processed}/{total} ({pct:.1f}%) | {n_api_calls} API calls | {n_failed} failed | ETA {remaining/60:.0f} min")

except KeyboardInterrupt:
    print("\n\nInterrupted. Progress saved (cache + jsonl).")
    print("Re-run to resume - cached papers will be skipped.")

elapsed = time.time() - start
print(f"\nDONE. Processed {n_processed}/{total} | {n_api_calls} API calls | {n_failed} failed | {elapsed/60:.1f} min total")
print(f"Output: {OUTPUT_PATH}")
