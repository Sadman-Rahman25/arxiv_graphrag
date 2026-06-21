"""Merge recovered references into papers.jsonl."""
import json
import shutil
from pathlib import Path

PAPERS_PATH = Path("data/raw/papers.jsonl")
RECOVERED_PATH = Path("data/raw/recovered_refs.jsonl")
MERGED_PATH = Path("data/raw/papers_merged.jsonl")
BACKUP_PATH = Path("data/raw/papers.jsonl.bak")


def main():
    recovered = {}
    if RECOVERED_PATH.exists():
        with open(RECOVERED_PATH, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("references"):
                    recovered[rec["paperId"]] = rec["references"]
    print(f"Loaded {len(recovered)} recovery records with non-empty refs")

    n_total = 0
    n_already = 0
    n_patched = 0
    n_missing = 0

    with open(PAPERS_PATH, encoding="utf-8") as fin, open(MERGED_PATH, "w", encoding="utf-8") as fout:
        for line in fin:
            paper = json.loads(line)
            n_total += 1
            paper_id = paper.get("paperId")

            if paper.get("references"):
                n_already += 1
            elif paper_id in recovered:
                paper["references"] = recovered[paper_id]
                n_patched += 1
            else:
                n_missing += 1

            fout.write(json.dumps(paper) + "\n")

    print(f"\nTotal papers:           {n_total}")
    print(f"Already had references: {n_already}")
    print(f"Patched from recovery:  {n_patched}")
    print(f"Still missing:          {n_missing}")
    print(f"Final coverage:         {(n_already + n_patched) / n_total * 100:.1f}%")

    shutil.copy(PAPERS_PATH, BACKUP_PATH)
    shutil.move(str(MERGED_PATH), str(PAPERS_PATH))
    print(f"\nReplaced {PAPERS_PATH} (backup at {BACKUP_PATH})")


if __name__ == "__main__":
    main()
