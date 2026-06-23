"""Day 9 Script 3 - Failure case extractor.

Pulls worst-scoring (question, retriever) cases and produces a human-readable
markdown report with full judge reasoning. Pure data extraction, no API calls.

Usage:
    python src/failure_cases.py
    python src/failure_cases.py --metric coverage --n 5
    python src/failure_cases.py --calibration
    python src/failure_cases.py --retriever dual --metric combined --n 3
"""
import argparse
import json
import re
import hashlib
from pathlib import Path
from datetime import datetime

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


def _cache_key(kind, model, *parts):
    h = hashlib.sha256()
    h.update(kind.encode()); h.update(b"||")
    h.update(model.encode())
    for p in parts:
        h.update(b"||"); h.update(p.encode())
    return h.hexdigest()


def extract_claims(answer_text, lookup):
    sentences = re.split(r'(?<=[.!?])\s+', answer_text)
    claims = []
    for sent in sentences:
        for bracket_match in re.finditer(r"\[([^\]]+)\]", sent):
            for p_match in re.finditer(r"P(\d+)", bracket_match.group(1)):
                tag = f"P{p_match.group(1)}"
                if tag in lookup:
                    claims.append({"tag": tag, "paperId": lookup[tag], "sentence": sent.strip()})
    return claims


def score_for_record(ans, expected_facts, cache, judge_model):
    faith_verdicts, cov_verdicts = [], []
    faith_counts = {"supported": 0, "partial": 0, "unsupported": 0}
    cov_counts   = {"present":   0, "partial": 0, "missing":     0}

    if ans.get("answer") and ans.get("lookup"):
        for c in extract_claims(ans["answer"], ans["lookup"]):
            key = _cache_key("faith", judge_model, c["paperId"], c["sentence"])
            if key in cache:
                v = cache[key]
                faith_verdicts.append({**c, **v})
                faith_counts[v["verdict"]] = faith_counts.get(v["verdict"], 0) + 1

    if ans.get("answer") and expected_facts:
        for fact in expected_facts:
            key = _cache_key("cov", judge_model, fact, ans["answer"])
            if key in cache:
                v = cache[key]
                cov_verdicts.append({"fact": fact, **v})
                cov_counts[v["verdict"]] = cov_counts.get(v["verdict"], 0) + 1

    ft = sum(faith_counts.values())
    fs = (faith_counts["supported"] + 0.5 * faith_counts["partial"]) / ft if ft else None
    ct = sum(cov_counts.values())
    cs = (cov_counts["present"] + 0.5 * cov_counts["partial"]) / ct if ct else None
    return fs, faith_verdicts, faith_counts, cs, cov_verdicts, cov_counts


def render_case(q, ans, fs, fv, fc, cs, cv, cc):
    out = []
    out.append(f"\n## {ans['question_id']} / {ans['retriever']}\n")
    scores = []
    if fs is not None: scores.append(f"**Faithfulness:** {fs:.3f}")
    if cs is not None: scores.append(f"**Coverage:** {cs:.3f}")
    out.append("  |  ".join(scores))
    out.append("")
    out.append(f"- **Regime:** {q['regime']}")
    out.append(f"- **Self-confidence:** {ans.get('confidence')}")
    out.append(f"- **Citations used:** {len(ans.get('citations', []))} of {len(ans.get('retrieved', []))} retrieved")
    out.append(f"- **Question:** {q['question']}")
    out.append("")
    out.append("### Generated Answer\n")
    out.append("> " + ans["answer"].replace("\n", "\n> "))
    out.append("")

    if fv:
        out.append(f"### Faithfulness verdicts ({fc['supported']}/{fc['partial']}/{fc['unsupported']} = supported/partial/unsupported)\n")
        emoji = {"supported": "[+]", "partial": "[~]", "unsupported": "[-]"}
        for v in fv:
            out.append(f"**[{v['tag']}] {emoji.get(v['verdict'], '[?]')} {v['verdict']}**")
            out.append(f"- Claim: _{v['sentence']}_")
            out.append(f"- Judge: {v['reasoning']}")
            out.append("")

    if cv:
        out.append(f"### Coverage verdicts ({cc['present']}/{cc['partial']}/{cc['missing']} = present/partial/missing)\n")
        emoji = {"present": "[+]", "partial": "[~]", "missing": "[-]"}
        for v in cv:
            out.append(f"**{emoji.get(v['verdict'], '[?]')} {v['verdict']}** — Expected: _{v['fact']}_")
            out.append(f"- Judge: {v['reasoning']}")
            out.append("")

    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metric", choices=["faithfulness", "coverage", "combined"], default="combined")
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--calibration", action="store_true")
    parser.add_argument("--retriever", default=None)
    parser.add_argument("--judge-model", default=JUDGE_MODEL)
    args = parser.parse_args()

    questions = {q["id"]: q for q in load_jsonl(GOLD_FILE)}
    facts     = {f["id"]: f["expected_facts"] for f in load_jsonl(FACTS_FILE)}
    answers   = load_jsonl(ANSWERS_FILE)
    cache     = load_cache()

    if args.retriever:
        answers = [a for a in answers if a["retriever"] == args.retriever]

    scored = []
    for ans in answers:
        q = questions.get(ans["question_id"])
        if not q:
            continue
        fs, fv, fc, cs, cv, cc = score_for_record(
            ans, facts.get(ans["question_id"], []), cache, args.judge_model
        )
        if fs is None and cs is None:
            continue
        scored.append({
            "ans": ans, "q": q,
            "faith_score": fs, "faith_verdicts": fv, "faith_counts": fc,
            "cov_score":   cs, "cov_verdicts":   cv, "cov_counts":   cc,
        })

    if not scored:
        print("No judged answers in cache. Run eval_answers.py first.")
        return

    if args.calibration:
        def k(s):
            conf = {"high": 3, "medium": 2, "low": 1, "abstain": 0}.get(s["ans"].get("confidence"), 0)
            sc = [x for x in [s["faith_score"], s["cov_score"]] if x is not None]
            q = sum(sc) / len(sc) if sc else 0.5
            return conf - 3 * q
        scored.sort(key=k, reverse=True)
        title = "Calibration failures (high confidence + low measured quality)"
    else:
        def k(s):
            if args.metric == "faithfulness":
                return s["faith_score"] if s["faith_score"] is not None else 99
            if args.metric == "coverage":
                return s["cov_score"] if s["cov_score"] is not None else 99
            sc = [x for x in [s["faith_score"], s["cov_score"]] if x is not None]
            return sum(sc) / len(sc) if sc else 99
        scored.sort(key=k)
        title = f"Worst {args.n} cases by {args.metric}"

    selected = scored[: args.n]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    md = [f"# Failure Case Report\n",
          f"**Selection:** {title}  ",
          f"**Generated:** {ts}  ",
          f"**Cases inspected (judged):** {len(scored)}  ",
          f"**Cases shown:** {len(selected)}  "]
    if args.retriever:
        md.append(f"**Filter:** retriever={args.retriever}  ")
    md.append("\n## Summary\n")
    md.append("| Q | Retriever | Faith | Cov | Conf | Regime |")
    md.append("|---|---|---:|---:|---|---|")
    for s in selected:
        fs = f"{s['faith_score']:.3f}" if s['faith_score'] is not None else "—"
        cs = f"{s['cov_score']:.3f}"   if s['cov_score']   is not None else "—"
        md.append(f"| {s['ans']['question_id']} | {s['ans']['retriever']} | {fs} | {cs} | "
                  f"{s['ans'].get('confidence')} | {s['q']['regime']} |")
    md.append("")

    for s in selected:
        md.append(render_case(
            s["q"], s["ans"],
            s["faith_score"], s["faith_verdicts"], s["faith_counts"],
            s["cov_score"],   s["cov_verdicts"],   s["cov_counts"],
        ))
        md.append("\n---\n")

    out_path = RESULTS_DIR / f"failure_cases_{ts}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"Failure Case Report — {title}")
    print(f"Cases shown: {len(selected)} of {len(scored)} judged\n")
    print(f"{'Q':<5} {'Retriever':<9} {'Faith':>7} {'Cov':>7} {'Conf':<8} Regime")
    print("-" * 65)
    for s in selected:
        fs = f"{s['faith_score']:.3f}" if s['faith_score'] is not None else "  —  "
        cs = f"{s['cov_score']:.3f}"   if s['cov_score']   is not None else "  —  "
        print(f"{s['ans']['question_id']:<5} {s['ans']['retriever']:<9} "
              f"{fs:>7} {cs:>7} {(s['ans'].get('confidence') or '?')[:8]:<8} {s['q']['regime']}")

    print(f"\nMarkdown report: {out_path}")


if __name__ == "__main__":
    main()