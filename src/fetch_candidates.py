"""
Phase 1 — Candidate metadata fetch (resumable, rate-limit aware).

Strategy:
  - Two-stage fetch (this is stage one, minimal metadata only)
  - Resume via token state file (so partial runs don't waste API quota)
  - Slow base pace + capped exponential backoff
"""

import os
import time
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

# --- config ---
load_dotenv()
API_KEY = os.getenv("SEMANTIC_SCHOLAR_KEY")
if not API_KEY:
    raise SystemExit("SEMANTIC_SCHOLAR_KEY not set in .env")

URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
HEADERS = {"x-api-key": API_KEY}

QUERY = ('"retrieval augmented generation" | "retrieval-augmented generation" '
         '| "dense passage retrieval" | RAG | GraphRAG | "dense retrieval"')
YEAR = "2022-2026"
FIELDS_OF_STUDY = "Computer Science"
FIELDS = "paperId,externalIds,title,year,citationCount,influentialCitationCount,fieldsOfStudy"

OUTPUT_PATH = Path("data/raw/candidates.jsonl")
STATE_PATH = Path("data/raw/.fetch_state.json")  # for resume capability
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# Tuning: S2 bulk endpoint is aggressive. 7s baseline keeps us under the burst threshold.
BASE_SLEEP = 7.0
MAX_RETRIES = 8
MAX_BACKOFF = 60.0   # cap individual backoff at 1 min


def load_state() -> dict:
    """Return saved fetch state if it exists, else fresh state."""
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"token": None, "page": 0, "total_seen": 0, "declared_total": None}


def save_state(state: dict) -> None:
    """Persist fetch state so we can resume on restart."""
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def fetch_page(token: str | None = None) -> dict:
    """Fetch one page with capped exponential backoff on 429."""
    params = {
        "query": QUERY,
        "year": YEAR,
        "fieldsOfStudy": FIELDS_OF_STUDY,
        "fields": FIELDS,
    }
    if token:
        params["token"] = token

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(URL, params=params, headers=HEADERS, timeout=60)
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

    raise SystemExit(f"Too many retries — aborting. State saved; rerun to resume.")


def main():
    state = load_state()

    # File mode depends on whether we're resuming
    mode = "a" if state["token"] is not None and state["total_seen"] > 0 else "w"
    if mode == "a":
        print(f"RESUMING from page {state['page']} (have {state['total_seen']} papers)")
    else:
        print("FRESH START")

    page = state["page"]
    token = state["token"]
    total_seen = state["total_seen"]
    declared_total = state["declared_total"]

    with open(OUTPUT_PATH, mode, encoding="utf-8") as f:
        while True:
            page += 1
            print(f"Page {page}: fetching... ", end="", flush=True)

            data = fetch_page(token)

            if declared_total is None:
                declared_total = data.get("total", "?")
                print(f"\n  API reports total = {declared_total}")
                print(f"Page {page}: ", end="")

            papers = data.get("data", [])
            token = data.get("token")

            for paper in papers:
                f.write(json.dumps(paper) + "\n")
                total_seen += 1
            f.flush()  # force write to disk so resume state stays consistent

            print(f"got {len(papers)} (cumulative: {total_seen}/{declared_total})")

            # Persist state after every successful page
            save_state({
                "token": token,
                "page": page,
                "total_seen": total_seen,
                "declared_total": declared_total,
            })

            if not token or not papers:
                break

            time.sleep(BASE_SLEEP)

    # Clean up state file on successful completion
    if STATE_PATH.exists():
        STATE_PATH.unlink()

    print(f"\nDONE. Saved {total_seen} candidate records to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()