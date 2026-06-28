"""Streamlit demo for arxiv-graphrag.

Dashboard-aesthetic UI: near-black background, mint accent, soft elevated
card system. Four retrievers (vector / graph / dual / dual_v2) over 3,500
arXiv papers on retrieval-augmented generation.

Run from project root:
    streamlit run app.py
"""

import html
import json
import logging
import os
import re
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Make src/ importable
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

logging.getLogger("neo4j").setLevel(logging.ERROR)

load_dotenv()

# ---- Project paths
EVAL_DIR = ROOT / "eval"
GOLD_FILE = EVAL_DIR / "gold_questions.jsonl"
ANSWERS_FILE = EVAL_DIR / "generated_answers.jsonl"
FACTS_FILE = EVAL_DIR / "expected_facts.jsonl"
RESULTS_DIR = EVAL_DIR / "results"

# ---- Constants
RETRIEVERS = ["dual_v2", "dual", "vector", "graph"]
RETRIEVER_DESC = {
    "dual_v2": "Dual retrieval + atomic-citation prompt (recommended)",
    "dual":    "Vector + graph traversal with adaptive RRF fusion",
    "vector":  "BGE-base dense embeddings only",
    "graph":   "Neo4j method/dataset bridges only",
}

EXAMPLE_QUESTIONS = [
    "How does Self-RAG decide when to retrieve, and how does that differ from active RAG?",
    "What techniques are used for hard negative mining in dense passage retrieval?",
    "How does Microsoft GraphRAG handle multi-document summarization at the corpus level?",
    "How does HyDE differ from query expansion approaches like Query2Doc?",
]


# ===========================================================
# THEME
# ===========================================================

def inject_theme() -> None:
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --bg:        #0d0e10;
    --card:      #181a1d;
    --card-2:    #1f2226;
    --card-3:    #262a2f;
    --line:      #2a2e33;
    --line-2:    #363a40;
    --text:      #ffffff;
    --text-dim:  #8a9099;
    --text-mute: #5c6168;
    --mint:      #b8e6d4;
    --mint-d:    #8ec8b3;
    --mint-bg:   rgba(184, 230, 212, 0.10);
    --rose:      #f0a890;
    --amber:     #e8c987;
}

.stApp {
    background: var(--bg);
}

/* Hide Streamlit chrome */
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDeployButton"] { display: none !important; }
.stDeployButton { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }

/* Hide default sidebar - we use inline retriever picker */
section[data-testid="stSidebar"] { display: none !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }

html, body, [class*="css"], .stMarkdown, p, span, div, label {
    font-family: 'Inter', sans-serif;
    color: var(--text);
    font-size: 14px;
    line-height: 1.55;
}

/* THE KEY FIX: constrain the actual Streamlit container */
.block-container {
    max-width: 1180px !important;
    margin: 0 auto !important;
    padding-top: 80px !important;
    padding-left: 32px !important;
    padding-right: 32px !important;
    padding-bottom: 60px !important;
}
@media (max-width: 768px) {
    .block-container {
        padding-top: 70px !important;
        padding-left: 16px !important;
        padding-right: 16px !important;
    }
}

/* ============ TOP BAR ============ */
.topbar {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 1000;
    background: var(--bg);
    border-bottom: 1px solid var(--line);
}
.topbar-inner {
    max-width: 1180px;
    margin: 0 auto;
    padding: 14px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
@media (max-width: 768px) {
    .topbar-inner { padding: 14px 16px; }
}

.logo { display: flex; align-items: center; gap: 10px; }
.logo-mark {
    width: 28px;
    height: 28px;
    border-radius: 8px;
    background: var(--mint);
    position: relative;
    display: grid;
    place-items: center;
}
.logo-mark::before {
    content: "";
    width: 12px;
    height: 12px;
    border: 2px solid var(--bg);
    border-radius: 50%;
}
.logo-mark::after {
    content: "";
    position: absolute;
    width: 6px;
    height: 6px;
    background: var(--bg);
    border-radius: 50%;
    bottom: 4px;
    right: 4px;
}
.logo-text {
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 14px;
    letter-spacing: -0.01em;
    color: var(--text);
}
.logo-text .accent { color: var(--mint); }

.topbar-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--text-mute);
    letter-spacing: 0.1em;
    text-transform: uppercase;
}
.topbar-meta .author { color: var(--mint-d); }

/* ============ GREETING ============ */
.greeting { margin-bottom: 18px; }
.greeting-eyebrow {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--mint);
    margin-bottom: 6px;
}
.greeting-title {
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 22px;
    line-height: 1.2;
    letter-spacing: -0.02em;
    color: var(--text);
}
@media (min-width: 900px) {
    .greeting-title { font-size: 28px; }
}
.greeting-title .accent { color: var(--mint); }
.greeting-sub {
    font-size: 13px;
    color: var(--text-dim);
    margin-top: 6px;
    line-height: 1.55;
    max-width: 640px;
}

/* ============ STAT GRID ============ */
.stat-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-bottom: 22px;
}
@media (min-width: 900px) {
    .stat-grid { grid-template-columns: repeat(4, 1fr); gap: 14px; }
}
.stat-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 14px;
}
@media (min-width: 900px) {
    .stat-card { padding: 18px; }
}
.stat-card.featured {
    background: linear-gradient(140deg, var(--mint-bg), var(--card));
    border-color: var(--mint-d);
}
.stat-icon {
    width: 32px;
    height: 32px;
    border-radius: 10px;
    background: var(--card-2);
    display: grid;
    place-items: center;
    margin-bottom: 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    color: var(--mint);
    font-weight: 600;
}
.stat-card.featured .stat-icon {
    background: var(--mint);
    color: var(--bg);
}
.stat-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-mute);
    margin-bottom: 4px;
}
.stat-value {
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 22px;
    line-height: 1;
    letter-spacing: -0.02em;
    color: var(--text);
}
@media (min-width: 900px) {
    .stat-value { font-size: 28px; }
}
.stat-card.featured .stat-value { color: var(--mint); }
.stat-delta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--text-dim);
    margin-top: 6px;
    letter-spacing: 0.04em;
}
.stat-delta.up { color: var(--mint-d); }

/* ============ SECTION HEAD ============ */
.sec-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 24px 0 10px 0;
}
.sec-head-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.20em;
    text-transform: uppercase;
    color: var(--text-mute);
}
.sec-head-action {
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    color: var(--mint);
    font-weight: 500;
}

/* ============ QUERY CARD ============ */
.query-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 16px;
    margin-bottom: 14px;
}
@media (min-width: 900px) {
    .query-card { padding: 22px; }
}

.question-display {
    background: var(--bg);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 12px 14px;
    margin: 10px 0 14px 0;
}
.question-display-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--text-mute);
    margin-bottom: 6px;
}
.question-display-text {
    font-size: 14px;
    line-height: 1.45;
    color: var(--text);
}

/* ============ ANSWER CARD ============ */
.answer-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 18px;
    margin-bottom: 14px;
}
@media (min-width: 900px) {
    .answer-card { padding: 22px 26px; }
}
.answer-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
    gap: 10px;
    flex-wrap: wrap;
}
.ret-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--mint);
    color: var(--bg);
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 5px 10px;
    border-radius: 6px;
}
.ret-badge::before {
    content: "";
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--bg);
}
.ret-badge.plain {
    background: var(--card-3);
    color: var(--text);
}
.ret-badge.plain::before { background: var(--mint); }

.conf-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--text-mute);
    letter-spacing: 0.04em;
}

.answer-text {
    font-size: 14.5px;
    line-height: 1.7;
    color: var(--text);
}
@media (min-width: 900px) {
    .answer-text { font-size: 15px; }
}
.answer-text p { margin-bottom: 12px; }
.answer-text .cite {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--mint);
    background: var(--mint-bg);
    padding: 1px 6px;
    border-radius: 4px;
    margin: 0 1px;
    font-weight: 500;
}

/* ============ METRICS STRIP ============ */
.metrics-strip {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 8px;
    margin-bottom: 18px;
}
@media (min-width: 900px) {
    .metrics-strip { gap: 12px; }
}
.metric-pill {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 14px 10px;
    text-align: center;
}
.metric-pill .lbl {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-mute);
    margin-bottom: 6px;
}
.metric-pill .val {
    font-family: 'Inter', sans-serif;
    font-size: 20px;
    font-weight: 700;
    line-height: 1;
    color: var(--text);
}
@media (min-width: 900px) {
    .metric-pill .val { font-size: 24px; }
}
.metric-pill .val.mint { color: var(--mint); }
.metric-pill .val.amber { color: var(--amber); }
.metric-pill .val.rose { color: var(--rose); }
.metric-pill .val.muted {
    color: var(--text-mute);
    font-style: italic;
    font-size: 16px;
    font-weight: 500;
}

/* ============ PAPERS ============ */
.paper {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 8px;
}
.paper.cited {
    border-color: var(--mint-d);
    background: linear-gradient(90deg, var(--mint-bg), var(--card) 35%);
}
.paper-head {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin-bottom: 6px;
}
.paper-tag {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    color: var(--mint);
    min-width: 32px;
}
.paper-tag.uncited { color: var(--text-mute); }
.paper-title {
    font-size: 13.5px;
    font-weight: 600;
    line-height: 1.35;
    flex: 1;
    color: var(--text);
}
.paper-pills {
    display: flex;
    gap: 6px;
    margin-bottom: 6px;
    margin-left: 42px;
    flex-wrap: wrap;
}
.pill {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    padding: 2px 7px;
    border-radius: 12px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.pill.year { background: var(--card-2); color: var(--text-dim); }
.pill.cited { background: var(--mint); color: var(--bg); font-weight: 600; }
.pill.meta { background: var(--card-2); color: var(--text-mute); }
.paper-abstract {
    font-size: 12.5px;
    line-height: 1.55;
    color: var(--text-dim);
    margin-left: 42px;
    font-style: italic;
}

/* ============ COMPARISON TABLE ============ */
.cmp-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 14px;
    overflow: hidden;
    margin-bottom: 14px;
}
.cmp-table {
    width: 100%;
    border-collapse: collapse;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
}
.cmp-table th {
    background: var(--card-2);
    text-align: left;
    padding: 11px 14px;
    font-size: 9px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-mute);
    font-weight: 500;
    border-bottom: 1px solid var(--line);
}
.cmp-table th.num { text-align: right; }
.cmp-table td {
    padding: 11px 14px;
    border-bottom: 1px solid var(--line);
    color: var(--text-dim);
}
.cmp-table tr:last-child td { border-bottom: none; }
.cmp-table td.num { text-align: right; font-weight: 500; }
.cmp-table tr.current td {
    background: var(--mint-bg);
    color: var(--text);
    font-weight: 600;
}
.cmp-table tr.current td:first-child::before {
    content: "▸ ";
    color: var(--mint);
}

/* ============ STREAMLIT WIDGET OVERRIDES ============ */

/* Radio horizontal as chip pills */
div[data-testid="stRadio"] > label { display: none; }
div[data-testid="stRadio"] > div { gap: 6px !important; }
div[data-testid="stRadio"] > div[role="radiogroup"] {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: wrap !important;
    gap: 6px !important;
}
div[data-testid="stRadio"] label[data-baseweb="radio"] {
    background: var(--card-2) !important;
    border: 1px solid var(--line) !important;
    border-radius: 8px !important;
    padding: 8px 12px !important;
    margin: 0 !important;
    cursor: pointer !important;
    transition: all 0.12s ease !important;
    flex: 1 !important;
    min-width: 0 !important;
    justify-content: center !important;
}
div[data-testid="stRadio"] label[data-baseweb="radio"]:hover {
    border-color: var(--mint-d) !important;
}
div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child {
    display: none !important;
}
div[data-testid="stRadio"] label[data-baseweb="radio"] p {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important;
    color: var(--text-dim) !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em !important;
    margin: 0 !important;
    text-align: center !important;
}
div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {
    background: var(--mint) !important;
    border-color: var(--mint) !important;
}
div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) p {
    color: var(--bg) !important;
    font-weight: 600 !important;
}

/* Buttons */
.stButton button {
    background: var(--card-2) !important;
    border: 1px solid var(--line) !important;
    color: var(--text) !important;
    border-radius: 10px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13px !important;
    text-align: left !important;
    min-height: 56px !important;
    padding: 12px 16px !important;
    line-height: 1.4 !important;
    transition: all 0.15s ease !important;
    width: 100% !important;
}
.stButton button:hover {
    border-color: var(--mint-d) !important;
    background: var(--card) !important;
    color: var(--text) !important;
}
.stButton button[kind="primary"] {
    background: var(--mint) !important;
    border-color: var(--mint) !important;
    color: var(--bg) !important;
    font-weight: 600 !important;
    text-align: center !important;
    min-height: 48px !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
    font-size: 12px !important;
}
.stButton button[kind="primary"]:hover {
    background: var(--mint-d) !important;
    border-color: var(--mint-d) !important;
}

/* Text area */
.stTextArea textarea {
    background: var(--bg) !important;
    border: 1px solid var(--line) !important;
    color: var(--text) !important;
    border-radius: 10px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 14px !important;
    padding: 12px 14px !important;
}
.stTextArea textarea:focus {
    border-color: var(--mint) !important;
    box-shadow: 0 0 0 1px var(--mint-bg) !important;
}
.stTextArea textarea::placeholder { color: var(--text-mute) !important; }

/* Select box */
.stSelectbox div[data-baseweb="select"] > div {
    background: var(--bg) !important;
    border: 1px solid var(--line) !important;
    border-radius: 10px !important;
    cursor: pointer !important;
    min-height: 44px !important;
}
.stSelectbox div[data-baseweb="select"] * { cursor: pointer !important; }
.stSelectbox div[data-baseweb="select"] > div > div {
    color: var(--text) !important;
    font-family: 'Inter', sans-serif !important;
}

/* Spinner */
.stSpinner > div { border-top-color: var(--mint) !important; }

/* Selection */
*:focus { outline: none !important; }
::selection { background: var(--mint); color: var(--bg); }

/* Scrollbar */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: var(--card); }
::-webkit-scrollbar-thumb { background: var(--line-2); border-radius: 5px; }
::-webkit-scrollbar-thumb:hover { background: var(--mint-d); }

/* Iframe (pyvis) wrap */
iframe { border-radius: 10px; }

/* Hide stale Streamlit spacing */
[data-testid="stVerticalBlock"] > [style*="flex-direction: column"] > [data-testid="stVerticalBlock"] {
    gap: 0 !important;
}
</style>
""", unsafe_allow_html=True)


# ===========================================================
# DATA LOADING (cached)
# ===========================================================

@st.cache_data
def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


@st.cache_data
def load_gold_questions() -> dict[str, dict]:
    return {q["id"]: q for q in load_jsonl(GOLD_FILE)}


@st.cache_data
def load_cached_answers() -> dict:
    out = {}
    for a in load_jsonl(ANSWERS_FILE):
        qid = a.get("question_id")
        ret = a.get("retriever")
        if qid and ret:
            out[(qid, ret)] = a
    return out


@st.cache_data
def load_latest_eval_data() -> dict:
    out = {}
    ret_files = sorted(RESULTS_DIR.glob("retrieval_eval_*.json"))
    if ret_files:
        with open(ret_files[-1], encoding="utf-8") as f:
            ret_data = json.load(f)
        for entry in ret_data.get("per_query", []):
            qid = entry.get("id")
            if not qid:
                continue
            for ret_name in ("vector", "graph", "dual"):
                block = entry.get(ret_name, {})
                out[(qid, ret_name)] = {"r10": block.get("recall@10")}
            dual_block = entry.get("dual", {})
            out[(qid, "dual_v2")] = {"r10": dual_block.get("recall@10")}

    for ret_name in RETRIEVERS:
        eval_files = sorted(RESULTS_DIR.glob(f"answer_eval_{ret_name}_*.json"))
        if not eval_files:
            continue
        with open(eval_files[-1], encoding="utf-8") as f:
            eval_data = json.load(f)
        for row in eval_data.get("per_question", []):
            qid = row.get("question_id")
            if not qid:
                continue
            key = (qid, ret_name)
            existing = out.get(key, {})
            existing["faith"] = row.get("faithfulness", {}).get("score")
            existing["cov"] = row.get("coverage", {}).get("score")
            existing["conf"] = row.get("confidence")
            out[key] = existing
    return out


@st.cache_resource(
    show_spinner="Loading retrieval models and Neo4j (first time only, ~30-60s)..."
)
def get_runtime():
    from neo4j import GraphDatabase
    from retrieve_vector import get_model
    from groq import Groq

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD")
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    get_model()
    groq_key = os.getenv("GROQ_API_KEY")
    groq_client = Groq(api_key=groq_key) if groq_key else None
    return {"driver": driver, "groq": groq_client}


# ===========================================================
# RUNTIME
# ===========================================================

def run_live_query(question: str, retriever: str, top_k: int = 10) -> dict:
    from retrieve_vector import vector_search
    from retrieve_graph import graph_search
    from retrieve_dual import dual_search
    from format_context import format_context
    from generate_answer import generate_cited_answer

    rt = get_runtime()
    driver = rt["driver"]

    if retriever == "vector":
        results = vector_search(driver, question, top_k=top_k)
    elif retriever == "graph":
        results = graph_search(driver, question, top_k=top_k, verbose=False)
    elif retriever in ("dual", "dual_v2"):
        results = dual_search(driver, question, top_k=top_k, verbose=False)
    else:
        raise ValueError(f"unknown retriever: {retriever}")

    for r in results:
        r.setdefault("hit_methods", [])
        r.setdefault("hit_datasets", [])
        r.setdefault("bridge_score", 0)
        r.setdefault("vector_rank", None)
        r.setdefault("graph_rank", None)

    context, lookup = format_context(driver, results)

    if retriever == "dual_v2":
        from run_modified_prompt import build_papers_block, generate_answer as gen_v2
        papers_block = build_papers_block(driver, results, lookup)
        parsed = gen_v2(
            rt["groq"],
            os.getenv("DUAL_V2_MODEL", "llama-3.3-70b-versatile"),
            question,
            papers_block,
        )
        answer_record = {
            "answer": parsed.get("answer", ""),
            "citations": parsed.get("citations", []),
            "confidence": parsed.get("confidence", "medium"),
            "retrieved": results,
            "lookup": lookup,
        }
    else:
        answer_record = generate_cited_answer(question, results, context, lookup)

    return answer_record


def get_cached_or_run(question: str, retriever: str, qid: str | None = None) -> dict:
    if qid:
        cached = load_cached_answers().get((qid, retriever))
        if cached:
            return cached
    return run_live_query(question, retriever)


# ===========================================================
# RENDERING
# ===========================================================

def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def linkify_citations(answer_text: str) -> str:
    escaped = _esc(answer_text)
    def replace_group(m):
        inner = m.group(1)
        tags = [t.strip() for t in inner.split(",")]
        return "".join(f'<span class="cite">{t}</span>' for t in tags)
    return re.sub(r"\[(P\d+(?:\s*,\s*P\d+)*)\]", replace_group, escaped)


def render_topbar() -> None:
    st.markdown("""
<div class="topbar">
  <div class="topbar-inner">
    <div class="logo">
      <div class="logo-mark"></div>
      <div class="logo-text">arxiv-<span class="accent">graphrag</span></div>
    </div>
    <div class="topbar-meta">by <span class="author">Sadman Rahman</span></div>
  </div>
</div>
""", unsafe_allow_html=True)


def render_greeting() -> None:
    st.markdown("""
<div class="greeting">
  <div class="greeting-eyebrow">Research dashboard</div>
  <div class="greeting-title">Graph-augmented retrieval over <span class="accent">3,500 RAG papers</span></div>
  <div class="greeting-sub">Compare four retrievers across 14 gold-annotated questions. Inspect citation drift, coverage gaps, and the dual_v2 prompt fix that closes the faithfulness gap.</div>
</div>
""", unsafe_allow_html=True)


def render_stats() -> None:
    st.markdown("""
<div class="stat-grid">
  <div class="stat-card">
    <div class="stat-icon">P</div>
    <div class="stat-label">Indexed papers</div>
    <div class="stat-value">3,500</div>
    <div class="stat-delta">66,089 edges</div>
  </div>
  <div class="stat-card">
    <div class="stat-icon">R</div>
    <div class="stat-label">Retrievers</div>
    <div class="stat-value">4</div>
    <div class="stat-delta">v · g · d · d2</div>
  </div>
  <div class="stat-card featured">
    <div class="stat-icon">F</div>
    <div class="stat-label">Faith gain</div>
    <div class="stat-value">+24.6</div>
    <div class="stat-delta up">dual_v2 vs dual</div>
  </div>
  <div class="stat-card">
    <div class="stat-icon">ρ</div>
    <div class="stat-label">Conf-Cov corr</div>
    <div class="stat-value">0.480</div>
    <div class="stat-delta">p &lt; 0.001</div>
  </div>
</div>
""", unsafe_allow_html=True)


def render_question_display(question: str, qid: str | None, regime: str | None) -> None:
    label = f"{qid} · {regime}" if qid and regime else (qid or "Custom question")
    st.markdown(f"""
<div class="question-display">
  <div class="question-display-label">{_esc(label)}</div>
  <div class="question-display-text">{_esc(question)}</div>
</div>
""", unsafe_allow_html=True)


def render_answer(record: dict, retriever: str) -> None:
    answer = record.get("answer", "(no answer)")
    confidence = record.get("confidence", "—")
    citations = record.get("citations", []) or []
    n_cites = len(citations)

    answer_html = linkify_citations(answer)
    badge_class = "ret-badge" if retriever == "dual_v2" else "ret-badge plain"

    st.markdown(f"""
<div class="answer-card">
  <div class="answer-head">
    <span class="{badge_class}">{retriever}</span>
    <span class="conf-meta">{_esc(confidence)} · {n_cites} citation{'s' if n_cites != 1 else ''}</span>
  </div>
  <div class="answer-text"><p>{answer_html}</p></div>
</div>
""", unsafe_allow_html=True)


def render_metrics_strip(qid: str, retriever: str) -> None:
    eval_data = load_latest_eval_data()
    metrics = eval_data.get((qid, retriever), {})
    if not metrics:
        return

    def fmt(val, kind="default"):
        if val is None:
            return '<span class="val muted">—</span>'
        cls = ""
        if kind == "perf":
            if val >= 0.7: cls = "mint"
            elif val < 0.4: cls = "rose"
            else: cls = "amber"
        return f'<span class="val {cls}">{val:.3f}</span>'

    r10 = metrics.get("r10")
    faith = metrics.get("faith")
    cov = metrics.get("cov")

    st.markdown(f"""
<div class="metrics-strip">
  <div class="metric-pill">
    <div class="lbl">Recall@10</div>
    {fmt(r10, "perf")}
  </div>
  <div class="metric-pill">
    <div class="lbl">Faith</div>
    {fmt(faith, "perf")}
  </div>
  <div class="metric-pill">
    <div class="lbl">Coverage</div>
    {fmt(cov, "perf")}
  </div>
</div>
""", unsafe_allow_html=True)


def render_papers(record: dict) -> None:
    retrieved = record.get("retrieved", []) or []
    lookup = record.get("lookup", {}) or {}
    citations = record.get("citations", []) or []

    cited_pids = set()
    for c in citations:
        if isinstance(c, dict):
            pid = c.get("paperId")
            if pid:
                cited_pids.add(pid)

    pid_to_tag = {pid: tag for tag, pid in lookup.items()}

    rt = get_runtime()
    driver = rt["driver"]

    def fetch_abstract(pid):
        with driver.session() as s:
            row = s.run(
                "MATCH (p:Paper {paperId: $pid}) RETURN p.abstract AS abstract",
                pid=pid
            ).single()
            return (row["abstract"] if row else None) or ""

    for paper in retrieved:
        pid = paper.get("paperId", "")
        tag = pid_to_tag.get(pid, "—")
        title = paper.get("title", "(no title)")
        year = paper.get("year", "")
        cite_count = paper.get("citationCount", 0)
        is_cited = pid in cited_pids

        abstract = fetch_abstract(pid)
        abstract_preview = abstract[:220] + ("…" if len(abstract) > 220 else "")

        tag_class = "paper-tag" if is_cited else "paper-tag uncited"
        card_class = "paper cited" if is_cited else "paper"

        pills = [f'<span class="pill year">{_esc(year)}</span>',
                 f'<span class="pill meta">{_esc(cite_count)} cites</span>']
        if is_cited:
            pills.append('<span class="pill cited">cited</span>')

        st.markdown(f"""
<div class="{card_class}">
  <div class="paper-head">
    <span class="{tag_class}">[{_esc(tag)}]</span>
    <span class="paper-title">{_esc(title)}</span>
  </div>
  <div class="paper-pills">{''.join(pills)}</div>
  <div class="paper-abstract">{_esc(abstract_preview)}</div>
</div>""", unsafe_allow_html=True)


def render_comparison_table(qid: str, current_retriever: str) -> None:
    eval_data = load_latest_eval_data()
    rows_html = []
    for ret in RETRIEVERS:
        m = eval_data.get((qid, ret), {})
        if not m:
            continue
        r10 = m.get("r10")
        faith = m.get("faith")
        cov = m.get("cov")
        r10_str = f"{r10:.3f}" if r10 is not None else "—"
        faith_str = f"{faith:.3f}" if faith is not None else "—"
        cov_str = f"{cov:.3f}" if cov is not None else "—"

        row_class = "current" if ret == current_retriever else ""

        rows_html.append(
            f'<tr class="{row_class}">'
            f'<td>{_esc(ret)}</td>'
            f'<td class="num">{r10_str}</td>'
            f'<td class="num">{faith_str}</td>'
            f'<td class="num">{cov_str}</td>'
            f'</tr>'
        )

    st.markdown(f"""
<div class="cmp-card">
  <table class="cmp-table">
    <thead>
      <tr>
        <th>Retriever</th>
        <th class="num">R@10</th>
        <th class="num">Faith</th>
        <th class="num">Cov</th>
      </tr>
    </thead>
    <tbody>{''.join(rows_html)}</tbody>
  </table>
</div>
""", unsafe_allow_html=True)


def render_subgraph(record: dict) -> None:
    try:
        from pyvis.network import Network
    except ImportError:
        st.info("pyvis not installed — skipping graph view.")
        return

    retrieved = record.get("retrieved", []) or []
    lookup = record.get("lookup", {}) or {}
    citations = record.get("citations", []) or []
    if not retrieved:
        return

    pid_to_tag = {pid: tag for tag, pid in lookup.items()}
    cited_pids = {c.get("paperId") for c in citations if isinstance(c, dict)}
    retrieved_pids = {p.get("paperId") for p in retrieved}

    rt = get_runtime()
    driver = rt["driver"]

    edges = []
    with driver.session() as s:
        result = s.run("""
            MATCH (a:Paper)-[r:CITES]->(b:Paper)
            WHERE a.paperId IN $pids AND b.paperId IN $pids
            RETURN a.paperId AS src, b.paperId AS dst
        """, pids=list(retrieved_pids))
        edges = [(row["src"], row["dst"]) for row in result]

    net = Network(
        height="380px",
        width="100%",
        bgcolor="#0d0e10",
        font_color="#ffffff",
        directed=True,
        notebook=False,
    )
    net.barnes_hut(spring_length=160, spring_strength=0.025)

    for paper in retrieved:
        pid = paper.get("paperId")
        if not pid:
            continue
        tag = pid_to_tag.get(pid, "?")
        title = paper.get("title", "")
        year = paper.get("year", "")
        is_cited = pid in cited_pids

        color = "#b8e6d4" if is_cited else "#262a2f"
        border = "#8ec8b3" if is_cited else "#363a40"
        size = 28 if is_cited else 14

        title_html = f"{tag}: {title}\n({year})"
        net.add_node(
            pid,
            label=tag,
            title=title_html,
            color={"background": color, "border": border},
            size=size,
            font={"face": "JetBrains Mono", "size": 13, "color": "#0d0e10" if is_cited else "#8a9099"},
        )

    for src, dst in edges:
        net.add_edge(src, dst, color="#363a40", width=1)

    html_str = net.generate_html(notebook=False)
    st.components.v1.html(html_str, height=400, scrolling=False)


# ===========================================================
# CALLBACKS
# ===========================================================

def use_example(example_text: str) -> None:
    st.session_state["mode_state"] = "Ask your own"
    st.session_state["question_input"] = example_text


# ===========================================================
# PAGE
# ===========================================================

st.set_page_config(
    page_title="arxiv-graphrag",
    layout="wide",
    page_icon="◆",
    initial_sidebar_state="collapsed",
)
inject_theme()

gold = load_gold_questions()

# ---- Top bar (fixed at viewport top, full width)
render_topbar()

# ---- Greeting
render_greeting()

# ---- Stats
render_stats()

# ============================================================
# QUERY SECTION
# ============================================================
st.markdown(
    '<div class="sec-head">'
    '<div class="sec-head-title">Query</div>'
    '<div class="sec-head-action">14 gold questions</div>'
    '</div>',
    unsafe_allow_html=True
)

# Mode toggle (Browse gold / Ask your own)
mode = st.radio(
    "mode",
    options=["Browse gold", "Ask your own"],
    index=0,
    horizontal=True,
    label_visibility="collapsed",
    key="mode_state",
)

# Question input depending on mode
selected_qid = None
selected_question = ""
selected_regime = None

if mode == "Browse gold":
    qid_options = sorted(gold.keys())
    qid_labels = [
        f"{qid} — {gold[qid]['question'][:60]}{'...' if len(gold[qid]['question']) > 60 else ''}"
        for qid in qid_options
    ]
    qid_idx = st.selectbox(
        "question",
        options=range(len(qid_options)),
        format_func=lambda i: qid_labels[i],
        label_visibility="collapsed",
    )
    selected_qid = qid_options[qid_idx]
    selected_question = gold[selected_qid]["question"]
    selected_regime = gold[selected_qid].get("regime", "")
    is_gold = True
else:
    selected_question = st.text_area(
        "question",
        placeholder="e.g., How do reranker architectures affect dense retrieval quality?",
        height=90,
        label_visibility="collapsed",
        key="question_input",
    )
    is_gold = False

# Display the selected question
if selected_question:
    render_question_display(selected_question, selected_qid, selected_regime)

# Retriever chips
st.markdown(
    '<div style="font-family: \'JetBrains Mono\', monospace; font-size: 9px; '
    'letter-spacing: 0.16em; text-transform: uppercase; color: var(--text-mute); '
    'margin: 4px 0 8px 0;">Retriever</div>',
    unsafe_allow_html=True
)
retriever = st.radio(
    "retriever",
    options=RETRIEVERS,
    index=0,
    horizontal=True,
    label_visibility="collapsed",
)

# Submit
submit = st.button("Retrieve and answer", type="primary")

# ============================================================
# EXAMPLES (only in Ask your own mode, after a results section)
# ============================================================
if not is_gold and not submit:
    st.markdown(
        '<div class="sec-head">'
        '<div class="sec-head-title">Try an example</div>'
        '<div class="sec-head-action">populates input</div>'
        '</div>',
        unsafe_allow_html=True
    )
    cols = st.columns(2)
    for i, ex in enumerate(EXAMPLE_QUESTIONS):
        with cols[i % 2]:
            st.button(ex, key=f"ex_{i}", on_click=use_example, args=(ex,))

# ============================================================
# RESULTS
# ============================================================
if submit:
    if not selected_question.strip():
        st.warning("Select or enter a question first.")
    else:
        with st.spinner(f"Running {retriever}..."):
            try:
                record = get_cached_or_run(
                    selected_question, retriever, qid=selected_qid
                )
            except Exception as e:
                st.error(f"Failed: {type(e).__name__}: {e}")
                st.stop()

        # Metrics strip (gold questions only)
        if is_gold and selected_qid:
            st.markdown(
                f'<div class="sec-head">'
                f'<div class="sec-head-title">Result · {selected_qid}</div>'
                f'<div class="sec-head-action">eval metrics</div>'
                f'</div>',
                unsafe_allow_html=True
            )
            render_metrics_strip(selected_qid, retriever)

        # Answer
        st.markdown(
            '<div class="sec-head">'
            '<div class="sec-head-title">Answer</div>'
            '<div class="sec-head-action">cited claims</div>'
            '</div>',
            unsafe_allow_html=True
        )
        render_answer(record, retriever)

        # Retrieved papers
        n_papers = len(record.get("retrieved", []))
        n_cited = len(record.get("citations", []))
        st.markdown(
            f'<div class="sec-head">'
            f'<div class="sec-head-title">Retrieved · {n_papers} papers</div>'
            f'<div class="sec-head-action">{n_cited} cited</div>'
            f'</div>',
            unsafe_allow_html=True
        )
        render_papers(record)

        # Subgraph
        st.markdown(
            '<div class="sec-head">'
            '<div class="sec-head-title">Citation subgraph</div>'
            '<div class="sec-head-action">mint = cited</div>'
            '</div>',
            unsafe_allow_html=True
        )
        render_subgraph(record)

        # Comparison table (gold only)
        if is_gold and selected_qid:
            st.markdown(
                f'<div class="sec-head">'
                f'<div class="sec-head-title">Cross-retriever · {selected_qid}</div>'
                f'<div class="sec-head-action">all 4</div>'
                f'</div>',
                unsafe_allow_html=True
            )
            render_comparison_table(selected_qid, retriever)

# Footer
st.markdown("""
<div style="margin-top: 40px; padding: 20px; border-top: 1px solid var(--line);
            font-family: 'JetBrains Mono', monospace; font-size: 10px;
            letter-spacing: 0.1em; color: var(--text-mute); text-align: center;
            text-transform: uppercase;">
· arxiv-graphrag · 
<a href="https://github.com/Sadman-Rahman25/arxiv_graphrag"
   style="color: var(--mint); text-decoration: none;">source on github</a>
</div>
""", unsafe_allow_html=True)