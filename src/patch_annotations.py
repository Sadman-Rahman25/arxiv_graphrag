"""Patch hand-drafted annotations into the gold_annotations template."""
import json
from pathlib import Path

TEMPLATE = Path("eval/gold_annotations_template.jsonl")
OUTPUT = Path("eval/gold_annotations.jsonl")

ANNOTATIONS = {
    1: {
        "methods": ["kg_rag", "rag", "knowledge_graph"],
        "datasets": [],
        "relations": [
            {"head": "kg_rag", "type": "INTRODUCES", "tail": None},
            {"head": "kg_rag", "type": "USES", "tail": "knowledge_graph"},
            {"head": "kg_rag", "type": "USES", "tail": "rag"},
        ],
        "notes": "Introduces specific KG-RAG pipeline for LLM agents. Eval datasets not visible in first 700 chars.",
    },
    2: {
        "methods": ["rag"],
        "datasets": ["legalbench"],
        "relations": [],
        "notes": "Assessment paper benchmarking commercial legal RAG tools. Doesn't introduce or train methods. Domain: legal.",
    },
    3: {
        "methods": ["rag"],
        "datasets": [],
        "relations": [],
        "notes": "Survey paper covering RAG broadly. Full method list would require reading body. No new INTRODUCES.",
    },
    4: {
        "methods": ["rag"],
        "datasets": [],
        "relations": [],
        "notes": "Introduces TrojRAG/BadRAG (adversarial attack). Not in gazetteer. Consider adding 'security' category - PoisonedRAG, BadRAG, TrojRAG, AgentPoison all appeared.",
    },
    5: {
        "methods": ["rag", "react"],
        "datasets": [],
        "relations": [],
        "notes": "Introduces RTLFixer (not in gazetteer) for Verilog debugging. Combines RAG + ReAct. Domain: hardware/EDA.",
    },
    6: {
        "methods": ["rag", "knowledge_graph"],
        "datasets": [],
        "relations": [
            {"head": "rag", "type": "USES", "tail": "knowledge_graph"},
        ],
        "notes": "Introduces GNN-RAG (not in gazetteer) - GNN + RAG hybrid for KGQA. Doesn't specify GNN architecture (GAT/GCN/GraphSAGE) in abstract. Datasets likely WebQuestionsSP/CWQ but not visible.",
    },
    7: {
        "methods": ["rag"],
        "datasets": [],
        "relations": [],
        "notes": "FlashRAG is an open-source RAG benchmarking toolkit, not a method. Reproduces existing RAG methods for comparison. May want 'framework/toolkit' category alongside method categories.",
    },
    8: {
        "methods": ["rag"],
        "datasets": ["multihop_rag"],
        "relations": [
            {"head": "multihop_rag", "type": "INTRODUCES", "tail": None},
            {"head": "rag", "type": "EVALUATED_ON", "tail": "multihop_rag"},
        ],
        "notes": "Paper introduces the MultiHop-RAG benchmark dataset for multi-hop queries. Confirms our dataset gazetteer entry is correctly canonical.",
    },
    9: {
        "methods": ["rag", "query_expansion"],
        "datasets": [],
        "relations": [],
        "notes": "Introduces DPA-RAG (not in gazetteer) - Dual Preference Alignment for RAG. 5 query augmentation strategies. Likely uses DPO-style preference optimization (not explicit in abstract).",
    },
    10: {
        "methods": ["rag"],
        "datasets": [],
        "relations": [],
        "notes": "Introduces BRAD agent system (not in gazetteer) for bioinformatics. Agentic RAG with LLMs + external tools + biomedical databases. No arxiv ID (Bioinformatics journal).",
    },
    11: {
        "methods": ["vit", "bert"],
        "datasets": [],
        "relations": [],
        "notes": "NOT a RAG paper - medical image analysis using ViT/DEiT/BeiT (DEiT, BeiT not in gazetteer). Matched the query loosely. Example of corpus drift - some papers are off-topic.",
    },
    12: {
        "methods": ["graphrag", "rag", "knowledge_graph"],
        "datasets": [],
        "relations": [
            {"head": "graphrag", "type": "USES", "tail": "knowledge_graph"},
        ],
        "notes": "Applies GraphRAG to supply chain/manufacturing. Custom supplier KG via ontology. Domain-specific application paper.",
    },
    13: {
        "methods": ["rag"],
        "datasets": [],
        "relations": [],
        "notes": "Introduces iRAG (not in gazetteer) - incremental RAG for video understanding. Domain: multimodal/video.",
    },
    14: {
        "methods": ["hybrid_search"],
        "datasets": [],
        "relations": [],
        "notes": "Generative recommendation systems paper. Introduces COBRA (not in gazetteer) - cascading sparse+dense retrieval. Borderline relevance - recsys-adjacent to RAG.",
    },
    15: {
        "methods": ["retriever_distillation"],
        "datasets": [],
        "relations": [],
        "notes": "Introduces CL-DRD (not in gazetteer) - curriculum learning for dense retriever distillation. Uses re-ranker as teacher. Likely MS MARCO eval (not visible in 700 chars).",
    },
    16: {
        "methods": ["rag", "gpt35"],
        "datasets": [],
        "relations": [
            {"head": "rag", "type": "USES", "tail": "gpt35"},
        ],
        "notes": "Introduces RareDxGPT (not in gazetteer). RAG over RareDis Corpus (custom, not in gazetteer). Domain: medical/rare disease.",
    },
    17: {
        "methods": ["rag"],
        "datasets": [],
        "relations": [],
        "notes": "Adobe product-specific RAG. 'Retrieval-aware finetuning' approach. Custom in-house QA dataset. Domain: customer support.",
    },
    18: {
        "methods": ["rag"],
        "datasets": [],
        "relations": [],
        "notes": "Introduces RadioRAG (not in gazetteer) - end-to-end online RAG for radiology QA. Domain: medical/radiology.",
    },
    19: {
        "methods": ["rag", "hybrid_search"],
        "datasets": [],
        "relations": [],
        "notes": "Blockchain traceability RAG chatbot. Multimodal (text + images + videos) via embeddings. Domain: agritech/blockchain.",
    },
    20: {
        "methods": [],
        "datasets": [],
        "relations": [],
        "notes": "Cloud operations multi-agent LLM framework. RAG/retrieval not explicitly mentioned in first 700 chars - borderline relevance. Domain: CloudOps. Possible corpus drift.",
    },
    21: {
        "methods": ["rag"],
        "datasets": [],
        "relations": [],
        "notes": "Introduces PennyLang dataset (not in gazetteer) - 3,347 quantum code samples for RAG-assisted code generation. Domain: quantum computing/PennyLane.",
    },
    22: {
        "methods": [],
        "datasets": [],
        "relations": [],
        "notes": "OFF-TOPIC - YOLO-based plant disease detection survey. Vision paper, not RAG. RAG mentioned only for one YOLO variant. Corpus drift. Domain: agriculture/CV.",
    },
    23: {
        "methods": ["rag"],
        "datasets": ["needle_haystack"],
        "relations": [],
        "notes": "Studies retrieval heads in long-context LLMs. Synthetic data fine-tuning. References 'needle/haystack' framing as methodology (overlaps with NIAH benchmark). Long-context research adjacent to RAG.",
    },
    24: {
        "methods": [],
        "datasets": [],
        "relations": [],
        "notes": "EMPTY ABSTRACT in source - only title visible. mAggretriever for multilingual dense retrieval. Likely MIRACL eval. Cannot annotate methodologies/datasets reliably without abstract.",
    },
    25: {
        "methods": ["rag"],
        "datasets": [],
        "relations": [],
        "notes": "Enterprise QA RAG (Adesso Turkiye internal). Custom data. Eval: ROUGE/BLEU/accuracy. Domain: enterprise knowledge management.",
    },
}


def main():
    recs = [json.loads(line) for line in open(TEMPLATE, encoding="utf-8")]
    n_patched = 0
    for rec in recs:
        aid = rec["annotation_id"]
        if aid in ANNOTATIONS:
            rec.update(ANNOTATIONS[aid])
            n_patched += 1

    with open(OUTPUT, "w", encoding="utf-8") as f:
        for rec in recs:
            f.write(json.dumps(rec) + "\n")

    print(f"Patched {n_patched} / {len(recs)} entries")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
