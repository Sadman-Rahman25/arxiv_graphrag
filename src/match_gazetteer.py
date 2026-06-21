"""Gazetteer matcher with word-boundary + case-sensitive matching.

Match rules:
  - Alias has any uppercase: case-sensitive + word boundaries
  - Alias is all lowercase:  case-insensitive + word boundaries
  - Alias has whitespace:    case-insensitive + word boundaries (treated as phrase)
"""
import json
import re
import yaml
from pathlib import Path


def build_pattern(alias: str) -> re.Pattern:
    """Compile a regex for an alias using shape-based rules."""
    alias = alias.strip()
    has_space = bool(re.search(r"\s", alias))
    has_upper = any(c.isupper() for c in alias)

    if has_space:
        return re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)
    elif has_upper:
        return re.compile(r"\b" + re.escape(alias) + r"\b")  # case-sensitive
    else:
        return re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)


def load_gazetteer_patterns(path: Path) -> dict:
    """Returns {canonical_id: [(alias, pattern), ...]}"""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    patterns = {}
    for canonical_id, info in data.items():
        compiled = []
        for alias in info.get("aliases", []):
            compiled.append((alias, build_pattern(alias)))
        patterns[canonical_id] = compiled
    return patterns


def find_matches(text: str, patterns: dict) -> dict:
    """Returns {canonical_id: [alias_that_matched, ...]}"""
    matches = {}
    for canonical_id, alias_patterns in patterns.items():
        for alias, pattern in alias_patterns:
            if pattern.search(text):
                matches.setdefault(canonical_id, []).append(alias)
    return matches


def main():
    print("Loading gazetteers...")
    methods_patterns = load_gazetteer_patterns(Path("gazetteer/methods.yaml"))
    datasets_patterns = load_gazetteer_patterns(Path("gazetteer/datasets.yaml"))
    print(f"  Methods:  {len(methods_patterns)} canonical IDs, "
          f"{sum(len(v) for v in methods_patterns.values())} total alias patterns")
    print(f"  Datasets: {len(datasets_patterns)} canonical IDs, "
          f"{sum(len(v) for v in datasets_patterns.values())} total alias patterns")

    INPUT = Path("data/raw/papers.jsonl")
    OUTPUT = Path("data/extractions/gazetteer_matches.jsonl")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    total_method_hits = 0
    total_dataset_hits = 0
    papers_with_methods = 0
    papers_with_datasets = 0

    with open(INPUT, encoding="utf-8") as fin, open(OUTPUT, "w", encoding="utf-8") as fout:
        for line in fin:
            paper = json.loads(line)
            title = paper.get("title") or ""
            abstract = paper.get("abstract") or ""
            text = title + "\n" + abstract

            method_matches = find_matches(text, methods_patterns)
            dataset_matches = find_matches(text, datasets_patterns)

            record = {
                "paperId": paper["paperId"],
                "title": title[:100],
                "methods": sorted(method_matches.keys()),
                "datasets": sorted(dataset_matches.keys()),
                "method_aliases": method_matches,
                "dataset_aliases": dataset_matches,
            }
            fout.write(json.dumps(record) + "\n")

            total += 1
            total_method_hits += len(method_matches)
            total_dataset_hits += len(dataset_matches)
            if method_matches:
                papers_with_methods += 1
            if dataset_matches:
                papers_with_datasets += 1

    print(f"\nProcessed {total:,} papers")
    print(f"Papers with at least one method match:  {papers_with_methods:,} ({100*papers_with_methods/total:.1f}%)")
    print(f"Papers with at least one dataset match: {papers_with_datasets:,} ({100*papers_with_datasets/total:.1f}%)")
    print(f"Avg methods per paper:  {total_method_hits/total:.2f}")
    print(f"Avg datasets per paper: {total_dataset_hits/total:.2f}")
    print(f"\nOutput: {OUTPUT}")


if __name__ == "__main__":
    main()
