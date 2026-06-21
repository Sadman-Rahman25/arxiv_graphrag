"""LLM extraction with tighter prompt and alias awareness."""
import os
import json
import time
import hashlib
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "llama-3.3-70b-versatile"
CACHE_DIR = Path("data/extractions/llm_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = """You are a precise scientific information extractor for a RAG/retrieval research corpus.

You MUST respond with valid JSON only. No markdown, no preamble.

JSON schema:
{
  "in_scope": true|false,
  "scope_reason": "brief one-sentence explanation",
  "methods_confirmed": ["canonical_id1", "canonical_id2"],
  "methods_novel": ["ProperNameMethod1"],
  "datasets_confirmed": ["canonical_id1"],
  "datasets_novel": ["ProperNameDataset1"],
  "relations": [
    {"head": "entity_name", "type": "INTRODUCES|USES|EVALUATED_ON", "tail": "entity_name_or_null"}
  ]
}

STRICT RULES:

1. IN_SCOPE: true if paper is about RAG, retrieval, dense/sparse search, knowledge graphs for LLMs, embeddings, or retrieval evaluation. False if primarily another field (CV, recsys, hardware, even if it mentions RAG in passing).

2. METHODS_CONFIRMED / DATASETS_CONFIRMED: from the gazetteer matches shown, list the canonical IDs the paper genuinely discusses. The gazetteer matches show you alias->canonical_id mappings so you can recognize that "WebQSP" maps to canonical "webquestions", "CWQ" to "complexwebqa", etc. Use canonical IDs only.

3. METHODS_NOVEL: must be a PROPER NAMED METHOD with a distinct identifier (e.g., "DPA-RAG", "RareDxGPT", "FlashRAG").
   FORBIDDEN: generic terms ("LLMs", "transformers", "RA-LLMs", "deep learning", "retrieval-augmented LLMs"), descriptive phrases ("our framework", "the proposed approach"), product/company names ("Lexis+ AI", "Westlaw", "ChatGPT-Plus"), or model variants without a distinct name ("Llama2-70B fine-tuned").
   If a method is already in confirmed list (by any alias), do NOT also list it as novel.

4. DATASETS_NOVEL: must be a PROPER NAMED DATASET (e.g., "PennyLang", "RareDis Corpus", "Adobe-QA").
   FORBIDDEN: generic phrases ("benchmark datasets", "training data", "the corpus", "our dataset"), descriptive language.

5. RELATIONS: 0-5 max. Head and tail must be ENTITIES YOU LISTED in methods_confirmed/novel or datasets_confirmed/novel. Use canonical IDs for confirmed entities, proper names for novel.
   FORBIDDEN: generic concepts ("LLM", "GNN", "neural network") as head/tail.
   - INTRODUCES: head is method/dataset this paper invents; tail is null
   - USES: head uses tail as a component
   - EVALUATED_ON: method head tested on dataset tail

Be conservative. When in doubt, leave the entity or relation out."""


def make_user_prompt(paper: dict, method_aliases: dict, dataset_aliases: dict) -> str:
    title = paper.get("title") or ""
    abstract = paper.get("abstract") or ""

    def format_aliases(d: dict) -> str:
        if not d:
            return "  (none)"
        return "\n".join(f"  {cid}: matched via [{', '.join(aliases)}]"
                         for cid, aliases in d.items())

    return f"""Paper title: {title}

Abstract:
{abstract}

Gazetteer matches (canonical_id : aliases found in text):
Methods:
{format_aliases(method_aliases)}
Datasets:
{format_aliases(dataset_aliases)}

Extract the JSON now."""


def cache_path(paper_id: str) -> Path:
    h = hashlib.md5(paper_id.encode()).hexdigest()
    return CACHE_DIR / h[:2] / f"{paper_id}.json"


def call_llm(system: str, user: str, retries: int = 2) -> dict | None:
    for attempt in range(retries + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.1,
                max_tokens=1000,
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content)
        except json.JSONDecodeError as e:
            print(f"    JSON parse error attempt {attempt+1}: {e}")
            if attempt < retries:
                time.sleep(2)
                continue
            return None
        except Exception as e:
            print(f"    API error attempt {attempt+1}: {e}")
            if attempt < retries:
                time.sleep(5)
                continue
            return None
    return None


def extract_for_paper(paper: dict, method_aliases: dict, dataset_aliases: dict, use_cache: bool = True) -> dict | None:
    paper_id = paper["paperId"]
    cf = cache_path(paper_id)
    if use_cache and cf.exists():
        return json.loads(cf.read_text(encoding="utf-8"))

    user_prompt = make_user_prompt(paper, method_aliases, dataset_aliases)
    result = call_llm(SYSTEM_PROMPT, user_prompt)
    if result is not None:
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def test_5_papers():
    gold_ids = {json.loads(line)["paperId"] for line in open("eval/gold_annotations.jsonl", encoding="utf-8")}
    gazetteer = {json.loads(line)["paperId"]: json.loads(line)
                 for line in open("data/extractions/gazetteer_matches.jsonl", encoding="utf-8")}

    count = 0
    for line in open("data/raw/papers.jsonl", encoding="utf-8"):
        paper = json.loads(line)
        if paper["paperId"] not in gold_ids:
            continue

        pid = paper["paperId"]
        gaz = gazetteer.get(pid, {"method_aliases": {}, "dataset_aliases": {}})

        print(f"\n=== Paper: {(paper['title'] or '')[:80]} ===")
        print(f"Gazetteer methods: {list(gaz.get('method_aliases', {}).keys())}")
        print(f"Gazetteer datasets: {list(gaz.get('dataset_aliases', {}).keys())}")
        print("Calling LLM (no cache)...")

        result = extract_for_paper(
            paper,
            gaz.get("method_aliases", {}),
            gaz.get("dataset_aliases", {}),
            use_cache=False,
        )

        if result is None:
            print("  [FAILED]")
        else:
            print(f"  In scope: {result.get('in_scope')} - {result.get('scope_reason')}")
            print(f"  Confirmed methods: {result.get('methods_confirmed')}")
            print(f"  Novel methods: {result.get('methods_novel')}")
            print(f"  Confirmed datasets: {result.get('datasets_confirmed')}")
            print(f"  Novel datasets: {result.get('datasets_novel')}")
            print(f"  Relations:")
            for rel in result.get("relations", [])[:5]:
                print(f"    {rel.get('head')} --{rel.get('type')}--> {rel.get('tail')}")

        count += 1
        if count >= 5:
            break
        time.sleep(1.5)


if __name__ == "__main__":
    test_5_papers()
