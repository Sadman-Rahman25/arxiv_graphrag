"""Day 6 - Groq-backed answer generation with citation contract.

Takes a question and a formatted context block, calls Groq Llama-3.3-70B
with a strict JSON output schema, and returns:
  {answer: str, citations: [str], confidence: str, model: str, cached: bool}

Implementation notes:
- temperature=0 for reproducibility during development. Raise on later iterations
  if answers feel templated.
- response_format={"type": "json_object"} enforces JSON at the API level.
- Schema validation on top of that catches partial responses / missing keys
  with a retry loop.
- Cache key = sha256(model + question + context). Changes to retrieval or prompt
  invalidate the cache automatically, so we never serve stale answers.
- Cache file at data/llm_cache/qa_cache.jsonl uses the same append-only JSONL
  pattern as Day 3 LLM extraction. Survives Ctrl+C, easy to inspect.
"""
import os
import json
import hashlib
import time
from pathlib import Path

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY  = os.getenv("GROQ_API_KEY")
DEFAULT_MODEL = "llama-3.3-70b-versatile"
CACHE_FILE    = Path("data/llm_cache/qa_cache.jsonl")
CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = """You are an expert research assistant specializing in retrieval-augmented generation (RAG) and related areas of NLP/IR research. You answer questions about academic papers by drawing on a provided set of retrieved papers.

CONTEXT FORMAT
Each retrieved paper is labeled with a tag [P1], [P2], etc. and includes its title, year, citation count, matched methods, and abstract.

ANSWER RULES
1. Answer ONLY using information present in the provided papers. Do not draw on general knowledge or speculate beyond what the papers state.
2. Every substantive claim must be supported by an inline citation in the form [P1] or [P1, P3] when multiple papers support the same claim.
3. If the provided papers do not contain enough information to answer the question, set confidence to "low" and explain what's missing rather than guessing.
4. Keep answers focused - 2-4 paragraphs typically, expandable for complex multi-part questions.
5. Prefer specific methodological or quantitative claims over vague summaries when the papers support them.
6. If the question asks about a comparison and only one side is covered by the papers, say so explicitly.

OUTPUT FORMAT (strict JSON, no markdown fences, no commentary outside the JSON)
{
  "answer": "Your answer with inline [P1] [P3] citations throughout.",
  "citations": ["P1", "P3"],
  "confidence": "high" | "medium" | "low"
}

The "citations" list should include every [Pn] tag that appears in your answer, in the order of first appearance."""


def _cache_key(model, question, context):
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(b"||")
    h.update(question.encode())
    h.update(b"||")
    h.update(context.encode())
    return h.hexdigest()


def _load_cache():
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


def _append_cache(key, response):
    with open(CACHE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"key": key, "response": response}) + "\n")


def _validate_response(parsed):
    """Validate the parsed JSON response against the citation contract schema."""
    for required in ("answer", "citations", "confidence"):
        if required not in parsed:
            raise ValueError(f"missing required key: {required}")
    if parsed["confidence"] not in ("high", "medium", "low"):
        raise ValueError(f"invalid confidence: {parsed['confidence']!r}")
    if not isinstance(parsed["citations"], list):
        raise ValueError("citations must be a list")
    if not isinstance(parsed["answer"], str) or not parsed["answer"].strip():
        raise ValueError("answer must be a non-empty string")


def generate_cited_answer(
    question,
    context,
    model=DEFAULT_MODEL,
    temperature=0.0,
    max_tokens=1500,
    use_cache=True,
    retries=2,
):
    """Generate a cited answer for a question given a context block.

    Returns dict {answer, citations, confidence, model, cached}.
    Raises RuntimeError after retries exhausted.
    """
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set in environment (.env)")

    key   = _cache_key(model, question, context)
    cache = _load_cache() if use_cache else {}
    if use_cache and key in cache:
        response = dict(cache[key])
        response["cached"] = True
        return response

    client = Groq(api_key=GROQ_API_KEY)
    user_message = (
        f"QUESTION:\n{question}\n\n"
        f"RETRIEVED PAPERS:\n{context}\n\n"
        f"Produce the JSON response now."
    )

    last_error = None
    for attempt in range(retries + 1):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens,
            )
            raw = completion.choices[0].message.content
            parsed = json.loads(raw)
            _validate_response(parsed)

            response = {
                "answer":     parsed["answer"],
                "citations":  parsed["citations"],
                "confidence": parsed["confidence"],
                "model":      model,
                "cached":     False,
            }

            if use_cache:
                _append_cache(key, response)

            return response

        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            print(f"  [attempt {attempt+1}] schema error: {e}")
            if attempt < retries:
                time.sleep(1)
                continue

        except Exception as e:
            last_error = e
            print(f"  [attempt {attempt+1}] API error: {type(e).__name__}: {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue

    raise RuntimeError(
        f"generate_cited_answer failed after {retries+1} attempts: {last_error}"
    )


if __name__ == "__main__":
    # Smoke test with a hardcoded mini-context (no Neo4j needed)
    sample_context = """[P1] Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection
     2023 | NeurIPS | 2,023 citations | methods: rag, self_rag
     Abstract: Despite their remarkable capabilities, large language models often produce factual inaccuracies. We introduce Self-Reflective Retrieval-Augmented Generation (Self-RAG), which adaptively retrieves passages on demand and reflects on its retrievals and generations using special tokens called reflection tokens.

[P2] Active Retrieval Augmented Generation
     2023 | EMNLP | 684 citations | methods: rag
     Abstract: A common limitation of RAG is single-pass retrieval. We propose FLARE, an active RAG pattern that triggers additional retrieval steps when generation confidence is low based on token probabilities."""

    sample_question = "How does Self-RAG decide when to retrieve, and how does that differ from active RAG?"

    print(f"Question: {sample_question}\n")
    response = generate_cited_answer(sample_question, sample_context)

    print(f"Confidence: {response['confidence']}  |  cached: {response['cached']}\n")
    print("ANSWER:")
    print(response["answer"])
    print(f"\nCitations: {response['citations']}")