"""Day 8 - LLM-judge based answer evaluation: faithfulness + coverage + calibration.

Reads:
  eval/gold_questions.jsonl     (questions, regimes)
  eval/expected_facts.jsonl     (hand-written facts per question)
  eval/generated_answers.jsonl  (output of generate_eval_answers.py)

For each (question, retriever) pair in generated_answers:
  1. FAITHFULNESS: for each unique [Pn] citation in the answer, extract the
     sentence containing it, ask the judge whether the cited paper's abstract
     supports the local claim. Verdicts: supported | partial | unsupported.

  2. COVERAGE: for each expected_fact for the question, ask the judge whether
     the answer states it. Verdicts: present | partial | missing.

  3. CALIBRATION: cross-tab self-reported confidence (high|medium|low) against
     measured (faithfulness, coverage) scores.

Saves per-judgment results to eval/judge_cache.jsonl (resumable cache) and
final aggregates to eval/results/answer_eval_<timestamp>.json.

Token budget warning: full pass on 14 questions x ~5 citations + 4 facts =
~120 judge calls per retriever. At ~1K tokens each, that's ~120K tokens on
70B. Free tier is 100K TPD. If you hit the limit, the cache means the next
day's run resumes seamlessly.
"""
import argparse
import os
import json
import re
import hashlib
import time
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict

logging.getLogger("neo4j").setLevel(logging.ERROR)

from neo4j import GraphDatabase
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

URI  = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PWD  = os.getenv("NEO4J_PASSWORD")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

GOLD_FILE     = Path("eval/gold_questions.jsonl")
FACTS_FILE    = Path("eval/expected_facts.jsonl")
ANSWERS_FILE  = Path("eval/generated_answers.jsonl")
CACHE_FILE    = Path("eval/judge_cache.jsonl")
RESULTS_DIR   = Path("eval/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_JUDGE_MODEL = "llama-3.3-70b-versatile"


# =====================================================================
# Judge prompts
# =====================================================================

FAITHFULNESS_SYSTEM = """You are evaluating whether a research paper's abstract supports a specific claim made in an answer.

You will be given:
  CLAIM: a sentence from a generated answer
  ABSTRACT: the abstract of the paper that was cited for that claim

Decide if the abstract supports the claim:
- "supported": the abstract directly states or strongly implies the claim
- "partial": the abstract is consistent with the claim but does not directly state it
- "unsupported": the abstract does not support the claim, or contradicts it

Be strict but fair. Generic restatements of the topic do not count as support;
the abstract must actually contain the substantive content of the claim.

Output strict JSON with no markdown:
{"verdict": "supported|partial|unsupported", "reasoning": "<one short sentence>"}"""

COVERAGE_SYSTEM = """You are checking whether a specific factual claim ("expected fact") is present in a generated answer.

You will be given:
  EXPECTED FACT: a factual claim that a good answer should contain
  ANSWER: the generated answer to evaluate

Decide if the answer contains this fact:
- "present": the answer clearly states the fact (paraphrasing is fine)
- "partial": the answer states a weaker or related version of the fact
- "missing": the answer does not state this fact at all

Be strict on "present" - the answer must actually convey the substantive content
of the expected fact, not just touch on the same topic.

Output strict JSON with no markdown:
{"verdict": "present|partial|missing", "reasoning": "<one short sentence>"}"""


# =====================================================================
# Cache management
# =====================================================================

def _cache_key(kind, model, *parts):
    h = hashlib.sha256()
    h.update(kind.encode())
    h.update(b"||")
    h.update(model.encode())
    for p in parts:
        h.update(b"||")
        h.update(p.encode())
    return h.hexdigest()


def load_cache():
    if not CACHE_FILE.exists():
        return {}
    cache = {}
    with open(CACHE_FILE, encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
                cache[row["key"]] = row["response"]
            except (json.JSONDecodeError, KeyError):
                continue
    return cache


def append_cache(key, response):
    with open(CACHE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"key": key, "response": response}) + "\n")


# =====================================================================
# Groq judge call
# =====================================================================

def judge_call(client, model, system_prompt, user_message, retries=2):
    last_err = None
    for attempt in range(retries + 1):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=300,
            )
            raw = completion.choices[0].message.content
            parsed = json.loads(raw)
            verdict = parsed.get("verdict")
            reasoning = parsed.get("reasoning", "")
            return {"verdict": verdict, "reasoning": reasoning}
        except Exception as e:
            last_err = e
            print(f"      judge attempt {attempt+1} error: {type(e).__name__}: {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"judge_call failed: {last_err}")


# =====================================================================
# Faithfulness scoring
# =====================================================================

def extract_claims(answer_text, lookup):
    """For each [Pn] occurrence in the answer, return (tag, paperId, sentence).

    A 'sentence' is the run of text from the previous full stop to the next.
    Cluster citations [P1, P3] produce one claim per P-tag with the same sentence.
    """
    sentences = re.split(r'(?<=[.!?])\s+', answer_text)

    claims = []
    pos = 0
    for sent in sentences:
        # find all [Pn] tags in this sentence
        for bracket_match in re.finditer(r"\[([^\]]+)\]", sent):
            for p_match in re.finditer(r"P(\d+)", bracket_match.group(1)):
                tag = f"P{p_match.group(1)}"
                if tag in lookup:
                    claims.append({
                        "tag":      tag,
                        "paperId":  lookup[tag],
                        "sentence": sent.strip(),
                    })
    return claims


def fetch_abstract(driver, paper_id):
    with driver.session() as s:
        row = s.run(
            "MATCH (p:Paper {paperId: $pid}) RETURN p.abstract AS abstract",
            pid=paper_id
        ).single()
        return (row["abstract"] if row else None) or ""


def score_faithfulness(client, driver, answer_record, judge_model, cache):
    """Judge each citation claim in the answer. Returns dict with verdicts."""
    answer = answer_record["answer"]
    lookup = answer_record["lookup"]

    if not answer or not lookup:
        return {
            "claims": [],
            "supported": 0, "partial": 0, "unsupported": 0,
            "score": None,
        }

    claims = extract_claims(answer, lookup)
    if not claims:
        return {
            "claims": [],
            "supported": 0, "partial": 0, "unsupported": 0,
            "score": None,
        }

    judgments = []
    counts = {"supported": 0, "partial": 0, "unsupported": 0}
    for c in claims:
        abstract = fetch_abstract(driver, c["paperId"])
        user_msg = (
            f"CLAIM: {c['sentence']}\n\n"
            f"ABSTRACT:\n{abstract or '(no abstract available)'}\n\n"
            f"Produce the JSON verdict."
        )
        key = _cache_key("faith", judge_model, c["paperId"], c["sentence"])
        if key in cache:
            verdict = cache[key]
            cached = True
        else:
            verdict = judge_call(client, judge_model, FAITHFULNESS_SYSTEM, user_msg)
            append_cache(key, verdict)
            cache[key] = verdict
            cached = False

        judgments.append({**c, **verdict, "cached": cached})
        counts[verdict["verdict"]] = counts.get(verdict["verdict"], 0) + 1

    total = sum(counts.values())
    # score: supported=1.0, partial=0.5, unsupported=0.0
    score = (counts["supported"] + 0.5 * counts["partial"]) / total if total else None

    return {
        "claims": judgments,
        "supported": counts["supported"],
        "partial": counts["partial"],
        "unsupported": counts["unsupported"],
        "score": score,
    }


# =====================================================================
# Coverage scoring
# =====================================================================

def score_coverage(client, answer_record, expected_facts, judge_model, cache):
    """Judge each expected fact against the answer."""
    answer = answer_record["answer"]
    if not answer or not expected_facts:
        return {
            "facts": [],
            "present": 0, "partial": 0, "missing": 0,
            "score": None,
        }

    judgments = []
    counts = {"present": 0, "partial": 0, "missing": 0}
    for fact in expected_facts:
        user_msg = (
            f"EXPECTED FACT: {fact}\n\n"
            f"ANSWER:\n{answer}\n\n"
            f"Produce the JSON verdict."
        )
        key = _cache_key("cov", judge_model, fact, answer)
        if key in cache:
            verdict = cache[key]
            cached = True
        else:
            verdict = judge_call(client, judge_model, COVERAGE_SYSTEM, user_msg)
            append_cache(key, verdict)
            cache[key] = verdict
            cached = False

        judgments.append({"fact": fact, **verdict, "cached": cached})
        counts[verdict["verdict"]] = counts.get(verdict["verdict"], 0) + 1

    total = sum(counts.values())
    score = (counts["present"] + 0.5 * counts["partial"]) / total if total else None

    return {
        "facts": judgments,
        "present": counts["present"],
        "partial": counts["partial"],
        "missing": counts["missing"],
        "score": score,
    }


# =====================================================================
# Main eval loop
# =====================================================================

def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--retriever",   default="dual",
                        help="Eval answers from this retriever only")
    parser.add_argument("--skip-faithfulness", action="store_true")
    parser.add_argument("--skip-coverage",     action="store_true")
    args = parser.parse_args()

    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")
    client = Groq(api_key=GROQ_API_KEY)

    questions = {q["id"]: q for q in load_jsonl(GOLD_FILE)}
    facts     = {f["id"]: f["expected_facts"] for f in load_jsonl(FACTS_FILE)}
    answers   = [a for a in load_jsonl(ANSWERS_FILE) if a["retriever"] == args.retriever]
    cache     = load_cache()

    print(f"Loaded {len(questions)} questions, {len(facts)} fact sets, "
          f"{len(answers)} answer records for retriever={args.retriever}")
    print(f"Judge model: {args.judge_model}")
    print(f"Cache: {len(cache)} prior judgments\n")

    driver = GraphDatabase.driver(URI, auth=(USER, PWD))

    per_question = []
    for ar in answers:
        qid = ar["question_id"]
        print(f"  {qid}  conf={ar.get('confidence')}  cites={len(ar.get('citations', []))}")

        faith = {"score": None}
        if not args.skip_faithfulness and ar.get("answer"):
            faith = score_faithfulness(client, driver, ar, args.judge_model, cache)
            print(f"      faithfulness: {faith['supported']}/{faith['partial']}/{faith['unsupported']} "
                  f"(s/p/u)  score={faith['score']:.3f}" if faith['score'] is not None
                  else f"      faithfulness: skipped (no claims)")

        cov = {"score": None}
        if not args.skip_coverage and ar.get("answer"):
            cov = score_coverage(client, ar, facts.get(qid, []), args.judge_model, cache)
            print(f"      coverage:     {cov['present']}/{cov['partial']}/{cov['missing']} "
                  f"(p/p/m)  score={cov['score']:.3f}" if cov['score'] is not None
                  else f"      coverage: skipped (no facts)")

        per_question.append({
            "question_id": qid,
            "regime":      questions[qid]["regime"],
            "retriever":   ar["retriever"],
            "confidence":  ar.get("confidence"),
            "faithfulness": faith,
            "coverage":     cov,
        })

    driver.close()

    # Aggregates
    f_scores = [r["faithfulness"]["score"] for r in per_question if r["faithfulness"]["score"] is not None]
    c_scores = [r["coverage"]["score"]     for r in per_question if r["coverage"]["score"]     is not None]
    agg = {
        "faithfulness_mean": sum(f_scores) / len(f_scores) if f_scores else 0.0,
        "coverage_mean":     sum(c_scores) / len(c_scores) if c_scores else 0.0,
        "n_evaluated":       len(per_question),
    }

    # Confidence calibration table
    calib = defaultdict(lambda: {"f_scores": [], "c_scores": [], "n": 0})
    for r in per_question:
        conf = r["confidence"]
        calib[conf]["n"] += 1
        if r["faithfulness"]["score"] is not None:
            calib[conf]["f_scores"].append(r["faithfulness"]["score"])
        if r["coverage"]["score"] is not None:
            calib[conf]["c_scores"].append(r["coverage"]["score"])

    print("\n" + "=" * 70)
    print(f"AGGREGATE (retriever={args.retriever})")
    print("=" * 70)
    print(f"  Faithfulness (mean): {agg['faithfulness_mean']:.3f}")
    print(f"  Coverage (mean):     {agg['coverage_mean']:.3f}")
    print(f"  N evaluated:         {agg['n_evaluated']}")

    print("\n" + "=" * 70)
    print("CONFIDENCE CALIBRATION")
    print("=" * 70)
    print(f"  {'Confidence':<12} {'N':>4}  {'Faithful':>10}  {'Coverage':>10}")
    print("  " + "-" * 42)
    for conf in ("high", "medium", "low", "abstain"):
        c = calib.get(conf, {})
        if not c.get("n"):
            continue
        f_mean = sum(c["f_scores"]) / len(c["f_scores"]) if c["f_scores"] else 0.0
        c_mean = sum(c["c_scores"]) / len(c["c_scores"]) if c["c_scores"] else 0.0
        print(f"  {conf:<12} {c['n']:>4}  {f_mean:>10.3f}  {c_mean:>10.3f}")

    print("\n" + "=" * 70)
    print("PER-QUESTION")
    print("=" * 70)
    print(f"  {'ID':<5} {'Regime':<28} {'Conf':<8} {'Faith':>7}  {'Cov':>7}")
    print("  " + "-" * 65)
    for r in per_question:
        fs = r["faithfulness"]["score"]
        cs = r["coverage"]["score"]
        print(f"  {r['question_id']:<5} {r['regime'][:28]:<28} {r['confidence'][:8]:<8} "
              f"{(fs if fs is not None else float('nan')):>7.3f}  "
              f"{(cs if cs is not None else float('nan')):>7.3f}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = RESULTS_DIR / f"answer_eval_{args.retriever}_{ts}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": ts,
            "retriever": args.retriever,
            "judge_model": args.judge_model,
            "aggregate": agg,
            "calibration": {k: {"n": v["n"],
                                 "f_mean": sum(v["f_scores"])/len(v["f_scores"]) if v["f_scores"] else None,
                                 "c_mean": sum(v["c_scores"])/len(v["c_scores"]) if v["c_scores"] else None}
                             for k, v in calib.items()},
            "per_question": per_question,
        }, f, indent=2)
    print(f"\nFull results saved to {out_file}")


if __name__ == "__main__":
    main()