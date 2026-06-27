"""Day 10 - dual_v2 experiment: generate answers with a revised prompt.

Hypothesis: dual's 2.5pt faithfulness deficit vs vector is driven by
citation density, NOT by retrieval quality. A prompt enforcing atomic
claims (one citation per sentence), verify-before-cite (each [Pn] tag
must support the local sentence), and specific naming (exact technique
names from abstracts) should reduce citation density while preserving
coverage.

Reuses the existing dual retriever - only the generation prompt changes.
Output is tagged retriever='dual_v2' and appended to generated_answers.jsonl
so the existing eval pipeline (eval_answers.py, diagnostic_report.py,
cross_retriever_comparison.py) picks it up via the --retriever flag.

CLI:
  python src/run_modified_prompt.py              # default: top-5 worst dual faith
  python src/run_modified_prompt.py --all        # all 14 questions
  python src/run_modified_prompt.py --qids q11,q14
  python src/run_modified_prompt.py --dry-run    # show what would run, no API calls

Token cost: ~3K per question. 14 questions -> ~42K tokens.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

# ----------------------------- paths -----------------------------

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

EVAL_DIR = ROOT / "eval"
ANSWERS_FILE = EVAL_DIR / "generated_answers.jsonl"
GOLD_FILE = EVAL_DIR / "gold_questions.jsonl"
RESULTS_DIR = EVAL_DIR / "results"

RETRIEVER_TAG = "dual_v2"
SOURCE_RETRIEVER = "dual"  # reuse the dual retriever's retrieved papers
DEFAULT_MODEL = "llama-3.3-70b-versatile"

# ----------------------------- prompt -----------------------------

DUAL_V2_SYSTEM = """You are answering a research question using ONLY the papers provided in the context. Follow these rules STRICTLY.

RULE 1 — ATOMIC CLAIMS, ONE CITATION PER SENTENCE
Each sentence makes ONE claim and cites AT MOST ONE paper.
NEVER write [P1, P3, P5] — split into separate sentences:
  WRONG: "Several methods address this [P1, P3, P5]."
  RIGHT: "Method X addresses this [P1]. Method Y takes a different approach [P3]. Method Z extends both [P5]."

RULE 2 — VERIFY BEFORE CITE
Before writing [Pn] at the end of a sentence, mentally verify that paper Pn's abstract directly supports the SPECIFIC claim in that sentence. If you cannot verify the connection, do not cite that paper — either remove the cite or pick a different paper that genuinely supports the claim.

RULE 3 — SPECIFIC NAMING
Use exact technique names from the abstracts. Do not paraphrase named methods into generic descriptions.
  WRONG: "Various reflection strategies are used."
  RIGHT: "Self-RAG uses learned reflection tokens [P1]."
  WRONG: "Some systems combine multiple retrievers."
  RIGHT: "RRF fusion combines vector and graph rankings [P3]."

RULE 4 — IF NOTHING SUPPORTS A POINT, OMIT IT
Do not pad with uncited generic statements. If the retrieved papers do not address an aspect of the question, do not invent a sentence about it.

RULE 5 — OUTPUT FORMAT
Respond in JSON with three fields:
  - "answer": the response text with inline [Pn] citations
  - "citations": a list of papers actually cited, each as {"tag": "P1", "paperId": "<id>", "title": "<title>"}
  - "confidence": one of "high", "medium", "low", "abstain"

Use "abstain" if NONE of the retrieved papers address the question — output the abstain confidence and a one-sentence explanation.
"""

USER_TEMPLATE = """QUESTION: {question}

RETRIEVED PAPERS:
{papers_block}

Produce the JSON response following all rules. Each citation must verify against the cited paper's abstract."""

# ----------------------------- loaders -----------------------------

def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_gold_questions():
    return {q["id"]: q for q in load_jsonl(GOLD_FILE)}


def load_existing_answers():
    """Returns (all_answers, set of qids already done for dual_v2)."""
    if not ANSWERS_FILE.exists():
        return [], set()
    all_ans = load_jsonl(ANSWERS_FILE)
    done = {a["question_id"] for a in all_ans if a.get("retriever") == RETRIEVER_TAG}
    return all_ans, done


def get_dual_retrieved_for(qid, all_answers):
    """Pull the retrieved papers from the existing dual answer for this qid.
    
    We reuse dual's retrieval so dual_v2 differs ONLY in the prompt.
    Returns (retrieved_list, lookup_dict, question_text) or (None, None, None).
    """
    for a in all_answers:
        if a["question_id"] == qid and a["retriever"] == SOURCE_RETRIEVER:
            return a.get("retrieved", []), a.get("lookup", {}), a.get("question")
    return None, None, None


def fetch_abstract(driver, paper_id):
    """Get abstract from Neo4j. Returns empty string if missing."""
    with driver.session() as s:
        row = s.run(
            "MATCH (p:Paper {paperId: $pid}) RETURN p.abstract AS abstract",
            pid=paper_id
        ).single()
        return (row["abstract"] if row else None) or ""


# ----------------------------- generation -----------------------------

def build_papers_block(driver, retrieved, lookup):
    """Format the retrieved papers into a numbered block for the prompt.
    
    lookup maps {"P1": "<paperId>", ...} - we honor that mapping so
    citation tags match the dual baseline.
    """
    # invert lookup: paperId -> tag
    pid_to_tag = {pid: tag for tag, pid in lookup.items()}
    
    lines = []
    for paper in retrieved:
        pid = paper.get("paperId")
        tag = pid_to_tag.get(pid, f"P?{pid[:6]}")
        title = paper.get("title", "(no title)")
        year = paper.get("year", "")
        abstract = fetch_abstract(driver, pid)
        lines.append(f"[{tag}] {title} ({year})")
        lines.append(f"    {abstract}")
        lines.append("")
    return "\n".join(lines)


def generate_answer(client, model, question, papers_block, retries=2):
    """One API call. Returns parsed JSON dict."""
    user_msg = USER_TEMPLATE.format(question=question, papers_block=papers_block)
    
    last_err = None
    for attempt in range(retries + 1):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": DUAL_V2_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=1500,
            )
            raw = completion.choices[0].message.content
            parsed = json.loads(raw)
            return parsed
        except Exception as e:
            last_err = e
            print(f"      generation attempt {attempt+1} error: {type(e).__name__}: {e}")
            if attempt < retries:
                import time
                time.sleep(2 ** attempt)
    raise RuntimeError(f"generation failed: {last_err}")


def append_answer(answer_record):
    """Append one answer to generated_answers.jsonl."""
    with open(ANSWERS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(answer_record) + "\n")


# ----------------------------- main -----------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true",
                        help="Run all 14 questions (default: top-5 worst dual faith)")
    parser.add_argument("--qids", type=str, default=None,
                        help="Comma-separated qids to run (e.g. q01,q11)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would run, no API calls")
    args = parser.parse_args()

    # Load environment
    load_dotenv(ROOT / ".env")
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key and not args.dry_run:
        raise RuntimeError("GROQ_API_KEY not set in .env")

    # Load data
    gold = load_gold_questions()
    all_answers, done = load_existing_answers()
    print(f"Loaded {len(gold)} gold questions")
    print(f"Existing answers: {len(all_answers)} total, "
          f"{len(done)} already done for {RETRIEVER_TAG}")

    # Determine target qids
    if args.qids:
        target_qids = [q.strip() for q in args.qids.split(",") if q.strip()]
    elif args.all:
        target_qids = sorted(gold.keys())
    else:
        # Default: top-5 worst dual faithfulness from Day 9 data
        # q01 (0.500), q02 (0.333), q11 (0.375), q12 (0.333), q14 (0.611)
        # Pick the 5 lowest:
        target_qids = ["q01", "q02", "q11", "q12", "q03"]
        print(f"\nDefault target: top-5 worst dual faithfulness questions")
        print(f"  ({', '.join(target_qids)})")
        print(f"  Use --all for all 14, or --qids to specify.")

    # Filter out already-done
    to_run = [q for q in target_qids if q not in done]
    skipped = [q for q in target_qids if q in done]
    
    if skipped:
        print(f"\nSkipping {len(skipped)} already-done: {skipped}")
    
    if not to_run:
        print(f"\nNothing to do — all target qids already in {ANSWERS_FILE}.")
        return

    print(f"\nWill generate {len(to_run)} dual_v2 answers: {to_run}")
    print(f"Estimated token cost: ~{3 * len(to_run)}K tokens")

    if args.dry_run:
        print("\n--dry-run set, exiting without API calls.")
        return

    # Setup clients
    print(f"\nModel: {args.model}")
    client = Groq(api_key=groq_key)
    
    # Neo4j connection (for fetching abstracts)
    from neo4j import GraphDatabase
    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "")
    driver = GraphDatabase.driver(uri, auth=(user, pwd))

    # Generate
    n_written = 0
    n_failed = 0
    for qid in to_run:
        print(f"\n  {qid}  generating dual_v2...")
        
        # Pull dual's retrieval for this question
        retrieved, lookup, question_text = get_dual_retrieved_for(qid, all_answers)
        if retrieved is None:
            print(f"    SKIP - no dual answer found for {qid}")
            n_failed += 1
            continue
        if not question_text:
            question_text = gold[qid].get("question", "")
        
        # Build papers block
        papers_block = build_papers_block(driver, retrieved, lookup)
        
        # Generate
        try:
            parsed = generate_answer(client, args.model, question_text, papers_block)
        except Exception as e:
            print(f"    FAILED: {type(e).__name__}: {e}")
            n_failed += 1
            # Check if it's rate limit - if so, stop entirely (resume next budget day)
            if "rate_limit" in str(e).lower() or "429" in str(e):
                print(f"\nRate limit hit. {n_written} answers written before cap.")
                print(f"Rerun the same command tomorrow to resume.")
                break
            continue

        # Build answer record matching the existing schema
        answer_record = {
            "question_id": qid,
            "question": question_text,
            "retriever": RETRIEVER_TAG,
            "retrieved": retrieved,
            "context_len": len(papers_block),
            "lookup": lookup,
            "answer": parsed.get("answer", ""),
            "citations": parsed.get("citations", []),
            "confidence": parsed.get("confidence", "medium"),
            "model": args.model,
            "cached": False,
            "prompt_version": "dual_v2",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }
        
        # Abstain check
        if answer_record["confidence"] == "abstain":
            answer_record["abstained"] = True

        append_answer(answer_record)
        n_written += 1
        
        cites = len(answer_record["citations"])
        conf = answer_record["confidence"]
        print(f"    (fresh)  conf={conf}  cites={cites}")

    driver.close()
    
    print(f"\n{'='*60}")
    print(f"Done. {n_written} dual_v2 answers written to {ANSWERS_FILE}")
    if n_failed:
        print(f"Failed: {n_failed}")
    print(f"\nNext steps (when budget allows):")
    print(f"  1. Judge:    python src/eval_answers.py --retriever {RETRIEVER_TAG}")
    print(f"  2. Analyze:  python src/cross_retriever_comparison.py")
    print(f"  3. Failure:  python src/failure_cases.py --retriever {RETRIEVER_TAG}")


if __name__ == "__main__":
    main()