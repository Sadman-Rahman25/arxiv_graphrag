"""
Phase 2 — Select top 3,500 papers by citation count.

Loads Phase 1 output, inspects citation/year distributions, picks the corpus,
and saves the selected IDs for Phase 3 (full-detail fetch).

Methodology decision logged in notebooks/Day2.md.
"""

import json
from collections import Counter
from pathlib import Path
from statistics import median

INPUT_PATH = Path("data/raw/candidates.jsonl")
OUTPUT_PATH = Path("data/raw/selected_ids.jsonl")
TARGET_SIZE = 3500


def load_candidates() -> list[dict]:
    """Load all candidate records into a list."""
    papers = []
    with open(INPUT_PATH, encoding="utf-8") as f:
        for line in f:
            papers.append(json.loads(line))
    return papers


def inspect(papers: list[dict]) -> None:
    """Print distributions to inform the selection methodology."""
    print(f"\n=== CANDIDATE POOL: {len(papers):,} papers ===\n")

    # Year distribution
    year_counts = Counter(p.get("year") for p in papers if p.get("year"))
    print("Papers per year:")
    for year in sorted(year_counts.keys()):
        bar = "#" * (year_counts[year] // 100)
        print(f"  {year}: {year_counts[year]:>5,}  {bar}")

    # Citation distribution
    cites = [p.get("citationCount", 0) or 0 for p in papers]
    cites_sorted = sorted(cites, reverse=True)
    print(f"\nCitation count stats:")
    print(f"  Max:         {cites_sorted[0]:,}")
    print(f"  Top 1%:      {cites_sorted[len(cites_sorted) // 100]:,}")
    print(f"  Top 10%:     {cites_sorted[len(cites_sorted) // 10]:,}")
    print(f"  Median:      {median(cites):.0f}")
    print(f"  Min:         {cites_sorted[-1]}")
    print(f"  Papers with 0 citations: {sum(1 for c in cites if c == 0):,}")

    # What does the cutoff at TARGET_SIZE look like?
    if len(cites_sorted) > TARGET_SIZE:
        cutoff = cites_sorted[TARGET_SIZE - 1]
        print(f"\nIf we take top {TARGET_SIZE:,} by citation:")
        print(f"  Cutoff citation count: {cutoff:,}")
        print(f"  (papers at exactly this count: {cites.count(cutoff)})")


def select_top_n_by_citations(papers: list[dict], n: int) -> list[dict]:
    """Sort by citationCount descending, take top n."""
    sorted_papers = sorted(
        papers,
        key=lambda p: (p.get("citationCount", 0) or 0),
        reverse=True,
    )
    return sorted_papers[:n]


def report_selection(selected: list[dict]) -> None:
    """Print stats on the selected corpus to confirm balance."""
    print(f"\n=== SELECTED CORPUS: {len(selected):,} papers ===\n")

    year_counts = Counter(p.get("year") for p in selected if p.get("year"))
    print("Selected papers per year:")
    for year in sorted(year_counts.keys()):
        bar = "#" * (year_counts[year] // 50)
        print(f"  {year}: {year_counts[year]:>5,}  {bar}")

    cites = [p.get("citationCount", 0) or 0 for p in selected]
    print(f"\nSelected citation count stats:")
    print(f"  Max:    {max(cites):,}")
    print(f"  Min:    {min(cites):,}")
    print(f"  Median: {median(cites):.0f}")


def save_selected(selected: list[dict]) -> None:
    """Save selected paper IDs + minimal metadata for Phase 3 to consume."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for paper in selected:
            # Keep just what Phase 3 needs to do the batch fetch
            record = {
                "paperId": paper["paperId"],
                "citationCount": paper.get("citationCount", 0),
                "year": paper.get("year"),
                "title": paper.get("title", ""),
            }
            f.write(json.dumps(record) + "\n")
    print(f"\nSaved {len(selected)} selected IDs to {OUTPUT_PATH}")


def main():
    papers = load_candidates()
    inspect(papers)
    selected = select_top_n_by_citations(papers, TARGET_SIZE)
    report_selection(selected)
    save_selected(selected)


if __name__ == "__main__":
    main()