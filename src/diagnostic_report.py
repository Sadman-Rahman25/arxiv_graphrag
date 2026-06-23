"""Day 9 - Per-question diagnostic report joining retrieval + answer eval.

Loads:
  eval/gold_questions.jsonl           - questions, regimes, gold paperIds
  eval/results/retrieval_eval_*.json  - latest retrieval eval (R@5/R@10/MRR)
  eval/generated_answers.jsonl        - confidences, citations per retriever
  eval/expected_facts.jsonl           - facts for coverage score lookup
  eval/judge_cache.jsonl              - faithfulness + coverage verdicts (partial)

For each (question, retriever):
  - Pulls regime + R@10 from retrieval eval
  - Pulls confidence + citation count from generated_answers
  - RECONSTRUCTS faithfulness + coverage scores from cache by re-deriving the
    same sha256 keys eval_answers.py uses (kind + model + content). No API calls.
  - Cells that haven't been judged yet show as '-' so the report works
    even mid-eval.

Output:
  - Console: per-question side-by-side table + aggregate-by-retriever
  - JSON: eval/results/diagnostic_<timestamp>.json for downstream scripts
"""
import argparse
import json
import re
import hashlib
import logging
from pathlib import Path
from datetime import datetime

logging.getLogger("neo4j").setLevel(logging.ERROR)

GOLD_FILE    = Path("eval/gold_questions.jsonl")
FACTS_FILE   = Path("eval/expected_facts.jsonl")
ANSWERS_FILE = Path("eval/generated_answers.jsonl")
JUDGE_CACHE  = Path("eval/judge_cache.jsonl")
RESULTS_DIR  = Path("eval/results")

JUDGE_MODEL = "llama-3.3-70b-versatile"


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_cache():
    if not JUDGE_CACHE.exists():
        return {}
    cache = {}
    with open(JUDGE_CACHE, encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
                cache[row["key"]] = row["response"]
            except (json.JSONDecodeError, KeyError):
                continue
    return cache


def load_latest_retrieval_eval():
    files = sorted(RESULTS_DIR.glob("retrieval_eval_*.json"))
    if not files:
        return None
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f)


def _cache_key(kind, model, *parts):
    h = hashlib.sha256()
    h.update(kind.encode()); h.update(b"||")
    h.update(model.encode())
    for p in parts:
        h.update(b"||"); h.update(p.encode())
    return h.hexdigest()


def extract_claims(answer_text, lookup):
    """Same logic as eval_answers.py."""
    sentences = re.split(r'(?<=[.!?])\s+', answer_text)
    claims = []
    for sent in sentences:
        for bracket_match in re.finditer(r"\[([^\]]+)\]", sent):
            for p_match in re.finditer(r"P(\d+)", bracket_match.group(1)):
                tag = f"P{p_match.group(1)}"
                if tag in lookup:
                    claims.append({"tag": tag, "paperId": lookup[tag], "sentence": sent.strip()})
    return claims


def reconstruct_faithfulness(answer_record, cache, judge_model):
    """Return (score, judged_count, total_count). score is None if nothing judged."""
    if not answer_record.get("answer") or not answer_record.get("lookup"):
        return None, 0, 0
    claims = extract_claims(answer_record["answer"], answer_record["lookup"])
    if not claims:
        return None, 0, 0

    counts = {"supported": 0, "partial": 0, "unsupported": 0}
    judged = 0
    for c in claims:
        key = _cache_key("faith", judge_model, c["paperId"], c["sentence"])
        if key in cache:
            v = cache[key]["verdict"]
            counts[v] = counts.get(v, 0) + 1
            judged += 1

    if judged == 0:
        return None, 0, len(claims)
    score = (counts["supported"] + 0.5 * counts["partial"]) / judged
    return score, judged, len(claims)


def reconstruct_coverage(answer_record, expected_facts, cache, judge_model):
    if not answer_record.get("answer") or not expected_facts:
        return None, 0, 0
    counts = {"present": 0, "partial": 0, "missing": 0}
    judged = 0
    for fact in expected_facts:
        key = _cache_key("cov", judge_model, fact, answer_record["answer"])
        if key in cache:
            v = cache[key]["verdict"]
            counts[v] = counts.get(v, 0) + 1
            judged += 1

    if judged == 0:
        return None, 0, len(expected_facts)
    score = (counts["present"] + 0.5 * counts["partial"]) / judged
    return score, judged, len(expected_facts)


def fmt_score(score, judged, total):
    """Format a score with '*' if partial, '-' if nothing judged."""
    if score is None:
        return "  -   "
    if judged < total:
        return f"{score:.2f}* "
    return f"{score:.3f} "


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge-model", default=JUDGE_MODEL)
    args = parser.parse_args()

    questions = {q["id"]: q for q in load_jsonl(GOLD_FILE)}
    facts     = {f["id"]: f["expected_facts"] for f in load_jsonl(FACTS_FILE)}
    answers   = load_jsonl(ANSWERS_FILE)
    cache     = load_cache()
    retrieval = load_latest_retrieval_eval()

    print(f"Loaded:")
    print(f"  Questions:        {len(questions)}")
    print(f"  Expected facts:   {len(facts)}")
    print(f"  Answer records:   {len(answers)}")
    print(f"  Judge cache:      {len(cache)} verdicts")
    print(f"  Retrieval eval:   {retrieval['timestamp'] if retrieval else 'NONE'}")
    print(f"  Judge model:      {args.judge_model}\n")

    retrieval_by_qid = {}
    if retrieval:
        for r in retrieval.get("per_query", []):
            retrieval_by_qid[r["id"]] = r

    answers_by_qr = {(a["question_id"], a["retriever"]): a for a in answers}

    diagnostics = []
    for qid in sorted(questions.keys()):
        q = questions[qid]
        ret_eval = retrieval_by_qid.get(qid, {})
        q_facts = facts.get(qid, [])

        per_retriever = {}
        for retriever in ("vector", "graph", "dual"):
            ans = answers_by_qr.get((qid, retriever))
            if ans is None:
                continue
            r10 = ret_eval.get(retriever, {}).get("recall@10") if ret_eval else None
            f_sc, f_j, f_t = reconstruct_faithfulness(ans, cache, args.judge_model)
            c_sc, c_j, c_t = reconstruct_coverage(ans, q_facts, cache, args.judge_model)

            per_retriever[retriever] = {
                "confidence":  ans.get("confidence"),
                "citations_n": len(ans.get("citations", [])),
                "recall_at_10": r10,
                "faithfulness":       f_sc,
                "faithfulness_judged": f_j, "faithfulness_total": f_t,
                "coverage":           c_sc,
                "coverage_judged":    c_j, "coverage_total":     c_t,
            }

        diagnostics.append({
            "question_id": qid,
            "question":    q["question"],
            "regime":      q["regime"],
            "gold_count":  len(q.get("relevant_paperIds", [])),
            "per_retriever": per_retriever,
        })

    # ===== Per-question side-by-side =====
    print("=" * 88)
    print("PER-QUESTION DIAGNOSTIC")
    print("=" * 88)
    for d in diagnostics:
        print(f"\n{d['question_id']} ({d['regime']})  gold={d['gold_count']}")
        print(f"  Q: {d['question'][:78]}")
        header = f"  {'Retriever':<8}  {'Conf':<7}  {'R@10':>6}  {'Cit':>3}  {'Faith':>7}  {'Cov':>7}"
        print(header)
        print(f"  {'-'*8}  {'-'*7}  {'-'*6}  {'-'*3}  {'-'*7}  {'-'*7}")
        for ret in ("vector", "graph", "dual"):
            d_r = d["per_retriever"].get(ret)
            if d_r is None:
                continue
            r10 = f"{d_r['recall_at_10']:.3f}" if d_r['recall_at_10'] is not None else "  -  "
            fs = fmt_score(d_r['faithfulness'], d_r['faithfulness_judged'], d_r['faithfulness_total'])
            cs = fmt_score(d_r['coverage'],    d_r['coverage_judged'],    d_r['coverage_total'])
            conf = (d_r['confidence'] or "-")[:7]
            print(f"  {ret:<8}  {conf:<7}  {r10:>6}  {d_r['citations_n']:>3}  {fs:>7}  {cs:>7}")

    # ===== Aggregate by retriever =====
    print("\n" + "=" * 88)
    print("AGGREGATE BY RETRIEVER")
    print("=" * 88)
    print(f"  {'Retriever':<8}  {'R@10':>7}  {'Faith':>10}  {'Cov':>10}  {'HighConf':>10}  {'Judged':>8}")
    print(f"  {'-'*8}  {'-'*7}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*8}")

    for retriever in ("vector", "graph", "dual"):
        per_r = [d["per_retriever"].get(retriever) for d in diagnostics if d["per_retriever"].get(retriever)]
        r10s = [d["recall_at_10"] for d in per_r if d["recall_at_10"] is not None]
        fs   = [d["faithfulness"] for d in per_r if d["faithfulness"] is not None]
        cs   = [d["coverage"]     for d in per_r if d["coverage"]     is not None]
        confs = [d["confidence"] for d in per_r]
        high  = sum(1 for c in confs if c == "high")

        r10_str = f"{sum(r10s)/len(r10s):.3f}" if r10s else "  -  "
        f_str   = f"{sum(fs)/len(fs):.3f}"     if fs   else "  -   "
        c_str   = f"{sum(cs)/len(cs):.3f}"     if cs   else "  -   "

        print(f"  {retriever:<8}  {r10_str:>7}  {f_str:>10}  {c_str:>10}  "
              f"{high}/{len(confs):<8}  {len(fs)}/{len(per_r):<6}")

    # Save JSON
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = RESULTS_DIR / f"diagnostic_{ts}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp":   ts,
            "judge_model": args.judge_model,
            "retrieval_eval_source": retrieval["timestamp"] if retrieval else None,
            "diagnostics": diagnostics,
        }, f, indent=2)

    print(f"\nSaved: {out_file}")
    print("\n* = partial judging (some claims/facts not yet in cache)")
    print("- = no judgments yet for this cell (waiting for eval_answers.py to run)")


if __name__ == "__main__":
    main()