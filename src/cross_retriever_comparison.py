"""Day 9 - Cross-retriever comparison aggregator (v3 - cache-correct).

Reads per-claim/per-fact judgments from eval/judge_cache.jsonl and
aggregates them to answer-level scores using the same formula as
eval_answers.py:

    faithfulness = (supported + 0.5*partial) / total_claims
    coverage     = (present   + 0.5*partial) / total_facts

An answer is 'judged' ONLY if 100% of its claims and 100% of its
expected_facts are in the cache. Partial judging shows '—'.

CLI:
  python src/cross_retriever_comparison.py
  python src/cross_retriever_comparison.py --retrievers dual,vector
  python src/cross_retriever_comparison.py --judge-model llama-3.3-70b-versatile
  python src/cross_retriever_comparison.py --facts-file eval/expected_facts.jsonl
  python src/cross_retriever_comparison.py --debug
"""

import argparse
import csv
import glob
import hashlib
import json
import re
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ----------------------------- paths -----------------------------

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "eval"
RESULTS_DIR = EVAL_DIR / "results"
ANSWERS_FILE = EVAL_DIR / "generated_answers.jsonl"
GOLD_FILE = EVAL_DIR / "gold_questions.jsonl"
CACHE_FILE = EVAL_DIR / "judge_cache.jsonl"

FACTS_CANDIDATES = [
    EVAL_DIR / "expected_facts.jsonl",
    EVAL_DIR / "facts.jsonl",
    EVAL_DIR / "eval_facts.jsonl",
    EVAL_DIR / "gold_facts.jsonl",
]

DEFAULT_RETRIEVERS = ["dual", "vector", "graph", "dual_v2"]
DEFAULT_JUDGE_MODEL = "llama-3.3-70b-versatile"


# ---------- EXACT replicas of eval_answers.py (byte-for-byte) ----------

def _cache_key(kind, model, *parts):
    h = hashlib.sha256()
    h.update(kind.encode())
    h.update(b"||")
    h.update(model.encode())
    for p in parts:
        h.update(b"||")
        h.update(p.encode())
    return h.hexdigest()


def extract_claims(answer_text, lookup):
    sentences = re.split(r'(?<=[.!?])\s+', answer_text)
    claims = []
    for sent in sentences:
        for bracket_match in re.finditer(r"\[([^\]]+)\]", sent):
            for p_match in re.finditer(r"P(\d+)", bracket_match.group(1)):
                tag = f"P{p_match.group(1)}"
                if tag in lookup:
                    claims.append({
                        "tag": tag,
                        "paperId": lookup[tag],
                        "sentence": sent.strip(),
                    })
    return claims


# ----------------------------- loaders -----------------------------

def find_facts_file(explicit=None):
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = ROOT / p
        return p if p.exists() else None
    for p in FACTS_CANDIDATES:
        if p.exists():
            return p
    return None


def load_facts(path):
    out = {}
    if path is None or not path.exists():
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            qid = row.get("id") or row.get("question_id") or row.get("qid")
            facts = row.get("expected_facts") or row.get("facts") or []
            if qid and facts:
                out[qid] = facts
    return out


def load_judge_cache():
    cache = {}
    if not CACHE_FILE.exists():
        return cache
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                cache[row["key"]] = row["response"]
            except (json.JSONDecodeError, KeyError):
                continue
    return cache


def load_latest_retrieval_eval():
    pattern = str(RESULTS_DIR / "retrieval_eval_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No retrieval_eval_*.json in {RESULTS_DIR}")
    latest = files[-1]
    with open(latest, "r", encoding="utf-8") as f:
        return latest, json.load(f)


def load_gold_questions():
    out = {}
    if not GOLD_FILE.exists():
        return out
    with open(GOLD_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            qid = row.get("id") or row.get("question_id") or row.get("qid")
            if qid:
                out[qid] = row
    return out


def load_all_answers():
    if not ANSWERS_FILE.exists():
        raise FileNotFoundError(f"Missing {ANSWERS_FILE}")
    out = []
    with open(ANSWERS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


# ----------------------------- scoring -----------------------------

def score_answer_faithfulness(answer_record, cache, judge_model):
    """Returns (score, n_claims, n_cached). Score is None if any uncached."""
    answer_text = answer_record.get("answer")
    lookup = answer_record.get("lookup", {})
    if not answer_text or not lookup:
        return None, 0, 0

    claims = extract_claims(answer_text, lookup)
    if not claims:
        return None, 0, 0

    counts = {"supported": 0, "partial": 0, "unsupported": 0}
    n_cached = 0
    for c in claims:
        key = _cache_key("faith", judge_model, c["paperId"], c["sentence"])
        if key in cache:
            n_cached += 1
            v = cache[key].get("verdict")
            if v in counts:
                counts[v] += 1

    if n_cached < len(claims):
        return None, len(claims), n_cached

    total = sum(counts.values())
    if total == 0:
        return None, len(claims), n_cached
    score = (counts["supported"] + 0.5 * counts["partial"]) / total
    return score, len(claims), n_cached


def score_answer_coverage(answer_record, expected_facts, cache, judge_model):
    """Returns (score, n_facts, n_cached). Score is None if any uncached."""
    answer_text = answer_record.get("answer")
    if not answer_text or not expected_facts:
        return None, 0, 0

    counts = {"present": 0, "partial": 0, "missing": 0}
    n_cached = 0
    for fact in expected_facts:
        key = _cache_key("cov", judge_model, fact, answer_text)
        if key in cache:
            n_cached += 1
            v = cache[key].get("verdict")
            if v in counts:
                counts[v] += 1

    if n_cached < len(expected_facts):
        return None, len(expected_facts), n_cached

    total = sum(counts.values())
    if total == 0:
        return None, len(expected_facts), n_cached
    score = (counts["present"] + 0.5 * counts["partial"]) / total
    return score, len(expected_facts), n_cached


# ----------------------------- retrieval metrics -----------------------------

def get_retrieval_metrics(per_query_entry, retriever):
    src = "dual" if retriever == "dual_v2" else retriever
    block = per_query_entry.get(src, {})
    return {
        "r5": block.get("recall@5"),
        "r10": block.get("recall@10"),
        "mrr": block.get("mrr"),
    }


# ----------------------------- row assembly -----------------------------

def build_per_question_rows(retrieval_eval, answers, gold_q, facts_map,
                            retrievers, cache, judge_model, debug=False):
    retrieval_idx = {}
    regimes = {}
    per_query = retrieval_eval.get("per_query", [])
    for entry in per_query:
        qid = entry.get("id")
        if not qid:
            continue
        retrieval_idx[qid] = {}
        regimes[qid] = entry.get("regime", "")
        for rname in retrievers:
            retrieval_idx[qid][rname] = get_retrieval_metrics(entry, rname)

    answer_idx = defaultdict(dict)
    for a in answers:
        qid = a.get("question_id")
        retriever = a.get("retriever")
        if qid and retriever:
            answer_idx[qid][retriever] = a

    rows = []
    qids = sorted(set(retrieval_idx.keys()) | set(answer_idx.keys()))
    for qid in qids:
        expected_facts = facts_map.get(qid, [])
        regime = regimes.get(qid) or gold_q.get(qid, {}).get("regime", "")

        for retriever in retrievers:
            ans = answer_idx.get(qid, {}).get(retriever)
            faith_score, n_claims, n_claims_cached = None, 0, 0
            cov_score, n_facts, n_facts_cached = None, 0, 0
            answer_present = ans is not None and bool(ans.get("answer"))
            abstained = ans.get("abstained", False) if ans else False

            if ans and not abstained:
                faith_score, n_claims, n_claims_cached = \
                    score_answer_faithfulness(ans, cache, judge_model)
                cov_score, n_facts, n_facts_cached = \
                    score_answer_coverage(ans, expected_facts, cache, judge_model)

            ret_metrics = retrieval_idx.get(qid, {}).get(retriever, {})
            judged = faith_score is not None or cov_score is not None

            rows.append({
                "qid": qid,
                "regime": regime,
                "retriever": retriever,
                "r5": ret_metrics.get("r5"),
                "r10": ret_metrics.get("r10"),
                "mrr": ret_metrics.get("mrr"),
                "faithfulness": faith_score,
                "coverage": cov_score,
                "n_claims": n_claims,
                "n_claims_cached": n_claims_cached,
                "n_facts": n_facts,
                "n_facts_cached": n_facts_cached,
                "answer_present": answer_present,
                "judged": judged,
                "abstained": abstained,
            })

            if debug and ans and not abstained:
                print(f"[debug] {qid} {retriever}: "
                      f"faith {n_claims_cached}/{n_claims}, "
                      f"cov {n_facts_cached}/{n_facts}")
    return rows


# ----------------------------- aggregation -----------------------------

def safe_mean(values):
    vs = [v for v in values if v is not None]
    return statistics.mean(vs) if vs else None


def aggregate_by_retriever(rows, retrievers):
    out = {}
    for r in retrievers:
        rs = [row for row in rows if row["retriever"] == r]
        out[r] = {
            "n_questions": len(rs),
            "n_answered": sum(1 for x in rs if x["answer_present"]),
            "n_abstained": sum(1 for x in rs if x["abstained"]),
            "n_judged": sum(1 for x in rs if x["judged"]),
            "mean_r5": safe_mean([x["r5"] for x in rs]),
            "mean_r10": safe_mean([x["r10"] for x in rs]),
            "mean_mrr": safe_mean([x["mrr"] for x in rs]),
            "mean_faithfulness": safe_mean([x["faithfulness"] for x in rs]),
            "mean_coverage": safe_mean([x["coverage"] for x in rs]),
        }
    return out


def pairwise_comparison(rows, retrievers, metric):
    by_qid = defaultdict(dict)
    for row in rows:
        v = row.get(metric)
        if v is not None:
            by_qid[row["qid"]][row["retriever"]] = v
    pairs = {}
    for i, a in enumerate(retrievers):
        for b in retrievers[i + 1:]:
            wins_a, wins_b, ties, n = 0, 0, 0, 0
            for qid, values in by_qid.items():
                if a in values and b in values:
                    n += 1
                    if values[a] > values[b]:
                        wins_a += 1
                    elif values[b] > values[a]:
                        wins_b += 1
                    else:
                        ties += 1
            pairs[(a, b)] = {"n": n, "wins_a": wins_a,
                             "wins_b": wins_b, "ties": ties}
    return pairs


# ----------------------------- rendering -----------------------------

def fmt(x, digits=3):
    return "—" if x is None else f"{x:.{digits}f}"


def render_markdown(rows, aggregates, pairs_r10, pairs_faith, pairs_cov,
                    retrievers, retrieval_eval_path, cache_count,
                    judge_model, facts_file):
    lines = []
    lines.append("# Cross-Retriever Comparison Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Retrieval eval source: `{Path(retrieval_eval_path).name}`")
    lines.append(f"Retrievers compared: {', '.join(retrievers)}")
    lines.append(f"Judge model: `{judge_model}`")
    lines.append(f"Judge cache: `eval/judge_cache.jsonl` ({cache_count} entries)")
    lines.append(f"Facts file: `{facts_file if facts_file else 'NOT FOUND'}`")
    lines.append("")

    lines.append("## Aggregate metrics")
    lines.append("")
    lines.append("| Retriever | n | answered | abstained | judged | R@5 | R@10 | MRR | Faithfulness | Coverage |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in retrievers:
        a = aggregates[r]
        lines.append(
            f"| {r} | {a['n_questions']} | {a['n_answered']} | "
            f"{a['n_abstained']} | {a['n_judged']} | "
            f"{fmt(a['mean_r5'])} | {fmt(a['mean_r10'])} | {fmt(a['mean_mrr'])} | "
            f"{fmt(a['mean_faithfulness'])} | {fmt(a['mean_coverage'])} |"
        )
    lines.append("")

    total_answered = sum(a["n_answered"] for a in aggregates.values())
    total_judged = sum(a["n_judged"] for a in aggregates.values())
    if total_answered:
        pct = 100.0 * total_judged / total_answered
        lines.append(f"**Judge coverage:** {total_judged}/{total_answered} "
                     f"answers fully judged ({pct:.1f}%).")
        if pct < 100:
            lines.append("")
            lines.append("*An answer counts as 'judged' only when every claim AND "
                         "every expected fact has a cache entry. Partials show '—' "
                         "and are excluded from aggregate means.*")
        lines.append("")

    def render_pairs(pairs, metric_name):
        block = [f"### Pairwise wins on {metric_name}", "",
                 "| A | B | n | A wins | B wins | ties |",
                 "|---|---|---:|---:|---:|---:|"]
        any_row = False
        for (a, b), d in pairs.items():
            if d["n"] == 0:
                continue
            block.append(f"| {a} | {b} | {d['n']} | {d['wins_a']} | "
                         f"{d['wins_b']} | {d['ties']} |")
            any_row = True
        block.append("")
        if any_row:
            lines.extend(block)

    lines.append("## Pairwise comparisons")
    lines.append("")
    render_pairs(pairs_r10, "Recall@10")
    render_pairs(pairs_faith, "Faithfulness")
    render_pairs(pairs_cov, "Coverage")

    lines.append("## Per-question grid")
    lines.append("")
    by_qid = defaultdict(dict)
    regimes = {}
    for row in rows:
        by_qid[row["qid"]][row["retriever"]] = row
        if row["regime"]:
            regimes[row["qid"]] = row["regime"]

    cols = ["qid", "regime"]
    for r in retrievers:
        cols += [f"{r} R@10", f"{r} faith", f"{r} cov"]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "|".join(["---"] * len(cols)) + "|")
    for qid in sorted(by_qid.keys()):
        cells = [qid, regimes.get(qid, "")]
        for r in retrievers:
            row = by_qid[qid].get(r, {})
            if row.get("abstained"):
                cells += ["abstain", "—", "—"]
            else:
                cells += [fmt(row.get("r10")),
                          fmt(row.get("faithfulness")),
                          fmt(row.get("coverage"))]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## Headline finding")
    lines.append("")
    def best(metric_key):
        best_r, best_v = None, -1.0
        for r in retrievers:
            v = aggregates[r].get(metric_key)
            if v is not None and v > best_v:
                best_v, best_r = v, r
        return best_r, best_v

    best_r10_r, best_r10_v = best("mean_r10")
    if best_r10_r:
        baseline = aggregates.get("vector", {}).get("mean_r10")
        if baseline and best_r10_r != "vector":
            lift = 100 * (best_r10_v - baseline) / baseline
            lines.append(f"- **{best_r10_r}** has the best mean Recall@10 at "
                         f"{best_r10_v:.3f}, a {lift:+.1f}% change vs the "
                         f"vector baseline ({baseline:.3f}).")
        else:
            lines.append(f"- **{best_r10_r}** has the best mean Recall@10 at "
                         f"{best_r10_v:.3f}.")

    best_f_r, best_f_v = best("mean_faithfulness")
    if best_f_r:
        lines.append(f"- **{best_f_r}** has the best mean faithfulness at "
                     f"{best_f_v:.3f} (across "
                     f"{aggregates[best_f_r]['n_judged']} fully-judged answers).")

    best_c_r, best_c_v = best("mean_coverage")
    if best_c_r:
        lines.append(f"- **{best_c_r}** has the best mean coverage at "
                     f"{best_c_v:.3f}.")

    lines.append("")
    return "\n".join(lines)


def render_csv(rows, path):
    fieldnames = ["qid", "regime", "retriever", "r5", "r10", "mrr",
                  "faithfulness", "coverage",
                  "n_claims", "n_claims_cached", "n_facts", "n_facts_cached",
                  "answer_present", "judged", "abstained"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ----------------------------- main -----------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retrievers", type=str,
                    default=",".join(DEFAULT_RETRIEVERS))
    ap.add_argument("--judge-model", type=str, default=DEFAULT_JUDGE_MODEL)
    ap.add_argument("--facts-file", type=str, default=None)
    ap.add_argument("--no-csv", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    retrievers = [r.strip() for r in args.retrievers.split(",") if r.strip()]
    print(f"Comparing retrievers: {retrievers}")
    print(f"Judge model:     {args.judge_model}")

    facts_file = find_facts_file(args.facts_file)
    facts_map = load_facts(facts_file)
    if facts_file:
        print(f"Facts file:      {facts_file} ({len(facts_map)} qids)")
    else:
        print(f"Facts file:      NOT FOUND (coverage will show '—')")

    cache = load_judge_cache()
    print(f"Judge cache:     {CACHE_FILE} ({len(cache)} entries)")

    retrieval_eval_path, retrieval_eval = load_latest_retrieval_eval()
    print(f"Retrieval eval:  {Path(retrieval_eval_path).name}")

    answers = load_all_answers()
    print(f"Answers loaded:  {len(answers)} entries")

    gold_q = load_gold_questions()
    print(f"Gold questions:  {len(gold_q)} loaded")

    rows = build_per_question_rows(retrieval_eval, answers, gold_q,
                                   facts_map, retrievers, cache,
                                   args.judge_model, debug=args.debug)
    print(f"Rows assembled:  {len(rows)} (qid x retriever)")

    n_judged = sum(1 for r in rows if r["judged"])
    n_answered = sum(1 for r in rows if r["answer_present"])
    print(f"Judge coverage:  {n_judged}/{n_answered} answers fully judged "
          f"({100 * n_judged / max(n_answered, 1):.1f}%)")

    aggregates = aggregate_by_retriever(rows, retrievers)
    pairs_r10 = pairwise_comparison(rows, retrievers, metric="r10")
    pairs_faith = pairwise_comparison(rows, retrievers, metric="faithfulness")
    pairs_cov = pairwise_comparison(rows, retrievers, metric="coverage")

    md = render_markdown(rows, aggregates, pairs_r10, pairs_faith,
                         pairs_cov, retrievers, retrieval_eval_path,
                         len(cache), args.judge_model, facts_file)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = RESULTS_DIR / f"cross_retriever_comparison_{stamp}.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"\nMarkdown:  {md_path}")

    if not args.no_csv:
        csv_path = RESULTS_DIR / f"cross_retriever_comparison_{stamp}.csv"
        render_csv(rows, csv_path)
        print(f"CSV:       {csv_path}")

    print("\nAggregate summary:")
    print(f"  {'retriever':<10} {'R@10':>8} {'Faith':>8} {'Cov':>8} {'judged':>8}")
    for r in retrievers:
        a = aggregates[r]
        print(f"  {r:<10} {fmt(a['mean_r10']):>8} "
              f"{fmt(a['mean_faithfulness']):>8} "
              f"{fmt(a['mean_coverage']):>8} {a['n_judged']:>8}")


if __name__ == "__main__":
    main()