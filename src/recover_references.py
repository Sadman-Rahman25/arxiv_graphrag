"""
Recover references for papers where S2 batch endpoint truncated them.

Strategy:
  - Identify papers with empty references in papers.jsonl
  - Sort by citationCount DESC (recover highest-impact first)
  - Use dedicated /paper/{id}/references endpoint
  - Save to side file (recovered_refs.jsonl); merge after
  - Resumable via tracking processed IDs
"""

import os
import time
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("SEMANTIC_SCHOLAR_KEY")
if not API_KEY:
    raise SystemExit("SEMANTIC_SCHOLAR_KEY not set in .env")

HEADERS = {"x-api-key": API_KEY}

PAPERS_PATH = Path("data/raw/papers.jsonl")
RECOVERED_PATH = Path("data/raw/recovered_refs.jsonl")
PROCESSED_PATH = Path("data/raw/.recovery_processed.txt")

# Tunable: recover top N missing-ref papers by citation count.
# Start small (e.g., 5) to test, then bump to 500 for a full recovery.
RECOVER_LIMIT = 500

BASE_SLEEP = 7.0
MAX_RETRIES = 8
MAX_BACKOFF = 60.0
REFS_LIMIT_PER_PAPER = 1000  # /references endpoint max

# Slim fields — drop nested authors to keep payload small
FIELDS = "citedPaper.paperId,citedPaper.title,citedPaper.year,citedPaper.externalIds"


def load_processed() -> set[str]:
    if PROCESSED_PATH.exists():
        return set(PROCESSED_PATH.read_text(encoding="utf-8").splitlines())
    return set()


def mark_processed(paper_id: str) -> None:
    with open(PROCESSED_PATH, "a", encoding="utf-8") as f:
        f.write(paper_id + "\n")


def fetch_references(paper_id: str) -> list[dict] | None:
    """Fetch all references for one paper. Returns list of citedPaper dicts."""
    url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/references"
    params = {"fields": FIELDS, "limit": REFS_LIMIT_PER_PAPER}

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=60)
            if r.status_code == 429:
                wait = min(BASE_SLEEP * (2 ** attempt), MAX_BACKOFF)
                print(f"    429 — backing off {wait:.0f}s")
                time.sleep(wait)
                continue
            if r.status_code == 404:
                return None  # paper not found, skip
            r.raise_for_status()
            data = r.json().get("data") or []  # handle null data field
            # Unwrap: each item has shape {"citedPaper": {...}}
            refs = [item["citedPaper"] for item in data if item.get("citedPaper")]
            return refs
        except requests.RequestException as e:
            wait = min(BASE_SLEEP * (2 ** attempt), MAX_BACKOFF)
            print(f"    Error: {e} — retrying in {wait:.0f}s")
            time.sleep(wait)

    print(f"    GIVING UP on {paper_id} after {MAX_RETRIES} retries")
    return None


def main():
    # Load papers, find those missing refs
    with open(PAPERS_PATH, encoding="utf-8") as f:
        papers = [json.loads(line) for line in f]

    missing = [p for p in papers if not p.get("references")]
    missing.sort(key=lambda p: p.get("citationCount", 0) or 0, reverse=True)
    print(f"Papers missing references: {len(missing)}")
    print(f"Recovery target: top {RECOVER_LIMIT} by citation count")

    # Resume support
    processed = load_processed()
    to_process = [p for p in missing[:RECOVER_LIMIT] if p["paperId"] not in processed]
    print(f"Already processed: {len(processed)}")
    print(f"To process this run: {len(to_process)}\n")

    if not to_process:
        print("Nothing to do. Move on to merge step.")
        return

    with open(RECOVERED_PATH, "a", encoding="utf-8") as out:
        for i, paper in enumerate(to_process, 1):
            pid = paper["paperId"]
            cites = paper.get("citationCount", 0)
            title = (paper.get("title") or "")[:60]
            print(f"[{i}/{len(to_process)}] cites={cites:>5} :: {title}")

            refs = fetch_references(pid)

            if refs is None:
                refs = []  # mark as attempted-but-empty so we don't retry

            out.write(json.dumps({"paperId": pid, "references": refs}) + "\n")
            out.flush()
            mark_processed(pid)

            print(f"    -> recovered {len(refs)} references")

            if i < len(to_process):
                time.sleep(BASE_SLEEP)

    print(f"\nDONE. Recovered refs saved to {RECOVERED_PATH}")
    print(f"Next: run merge_references.py to patch papers.jsonl")


if __name__ == "__main__":
    main()