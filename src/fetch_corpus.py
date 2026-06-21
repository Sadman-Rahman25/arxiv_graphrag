"""
Phase 3 — Full corpus fetch with references.

For each of the 3,500 papers selected in Phase 2, fetch:
  - Full metadata: title, abstract, authors, venue, fieldsOfStudy
  - References (the papers it cites) — up to ~100 per paper
  - Authors with affiliations

Uses POST /paper/batch (up to 500 IDs per call) — 7 calls instead of 3,500.

Resumable via batch-index state file.
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

URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
HEADERS = {"x-api-key": API_KEY, "Content-Type": "application/json"}

# All fields we need for the GraphRAG pipeline
FIELDS = ",".join([
    "paperId", "externalIds", "title", "abstract", "year",
    "venue", "publicationVenue", "publicationDate",
    "citationCount", "influentialCitationCount",
    "fieldsOfStudy", "s2FieldsOfStudy",
    "authors.authorId", "authors.name", "authors.affiliations",
    "references.paperId", "references.title", "references.year",
    "references.externalIds", "references.authors",
])

INPUT_PATH = Path("data/raw/selected_ids.jsonl")
OUTPUT_PATH = Path("data/raw/papers.jsonl")
STATE_PATH = Path("data/raw/.corpus_fetch_state.json")

BATCH_SIZE = 500       # S2 batch endpoint max
BASE_SLEEP = 7.0       # same pacing as Phase 1
MAX_RETRIES = 8
MAX_BACKOFF = 60.0


def load_state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"next_batch_idx": 0, "fetched_count": 0}


def save_state(state: dict) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def load_selected_ids() -> list[str]:
    """Load just the paperIds from Phase 2 output."""
    ids = []
    with open(INPUT_PATH, encoding="utf-8") as f:
        for line in f:
            ids.append(json.loads(line)["paperId"])
    return ids


def fetch_batch(ids: list[str]) -> list[dict | None]:
    """
    POST a batch of up to 500 paper IDs, get back full metadata for each.
    Returns a list parallel to `ids` — entries may be None if a paper was not found.
    """
    body = {"ids": ids}
    params = {"fields": FIELDS}

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(URL, json=body, params=params, headers=HEADERS, timeout=120)
            if r.status_code == 429:
                wait = min(BASE_SLEEP * (2 ** attempt), MAX_BACKOFF)
                print(f"    429 — backing off {wait:.0f}s (attempt {attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            wait = min(BASE_SLEEP * (2 ** attempt), MAX_BACKOFF)
            print(f"    Request error: {e} — retrying in {wait:.0f}s")
            time.sleep(wait)

    raise SystemExit("Too many retries — state saved, rerun to resume.")


def main():
    all_ids = load_selected_ids()
    print(f"Loaded {len(all_ids)} selected paper IDs")

    state = load_state()
    start_idx = state["next_batch_idx"]
    fetched_count = state["fetched_count"]

    # Split into batches of BATCH_SIZE
    batches = [all_ids[i:i + BATCH_SIZE] for i in range(0, len(all_ids), BATCH_SIZE)]
    print(f"Will fetch in {len(batches)} batches of up to {BATCH_SIZE} papers each")

    if start_idx > 0:
        print(f"RESUMING from batch {start_idx + 1} (already have {fetched_count} papers)")

    # Append if resuming, overwrite if fresh
    mode = "a" if start_idx > 0 else "w"

    with open(OUTPUT_PATH, mode, encoding="utf-8") as f:
        for i in range(start_idx, len(batches)):
            batch = batches[i]
            print(f"Batch {i + 1}/{len(batches)}: requesting {len(batch)} papers... ",
                  end="", flush=True)

            results = fetch_batch(batch)

            written = 0
            null_count = 0
            for paper in results:
                if paper is None:
                    null_count += 1
                    continue
                f.write(json.dumps(paper) + "\n")
                fetched_count += 1
                written += 1
            f.flush()

            print(f"got {written} (nulls: {null_count}) | cumulative: {fetched_count}")

            # Persist state after every successful batch
            save_state({
                "next_batch_idx": i + 1,
                "fetched_count": fetched_count,
            })

            # Pace between batches
            if i + 1 < len(batches):
                time.sleep(BASE_SLEEP)

    # Clean up state on success
    if STATE_PATH.exists():
        STATE_PATH.unlink()

    print(f"\nDONE. Saved {fetched_count} full paper records to {OUTPUT_PATH}")
    print(f"Next: Phase 4 (methods.yaml gazetteer) — no API calls needed.")


if __name__ == "__main__":
    main()