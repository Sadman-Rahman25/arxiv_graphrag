"""Verify all critical packages import and load."""

print("Testing core...")
import os
from dotenv import load_dotenv
load_dotenv()
print(f"  GROQ_API_KEY loaded: {bool(os.getenv('GROQ_API_KEY'))}")

print("Testing Groq...")
from groq import Groq
client = Groq()
resp = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Say 'ready' if you can hear me."}],
    max_tokens=10,
)
print(f"  Groq response: {resp.choices[0].message.content}")

print("Testing Chroma...")
import chromadb
chroma_client = chromadb.PersistentClient(path="./data/chroma_db_test")
col = chroma_client.create_collection("smoke_test")
col.add(documents=["hello world"], ids=["1"])
print(f"  Chroma stored docs: {col.count()}")
chroma_client.delete_collection("smoke_test")

print("Testing BM25...")
from rank_bm25 import BM25Okapi
bm25 = BM25Okapi([["hello", "world"], ["dense", "retrieval"]])
print(f"  BM25 scores: {bm25.get_scores(['retrieval'])}")

print("Testing sentence-transformers (BGE)...")
from sentence_transformers import SentenceTransformer
print("  Downloading BGE-large-en-v1.5 (this takes ~1 min first time)...")
model = SentenceTransformer("BAAI/bge-large-en-v1.5")
emb = model.encode("test query")
print(f"  Embedding shape: {emb.shape}")

print("Testing Neo4j driver (no connection yet)...")
from neo4j import GraphDatabase
print(f"  Neo4j driver imports OK")

print("\nALL PACKAGES VERIFIED")