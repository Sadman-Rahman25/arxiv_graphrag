import sys
print("Step 1: starting", flush=True)

from sentence_transformers import SentenceTransformer
print("Step 2: imported", flush=True)

m = SentenceTransformer("BAAI/bge-base-en-v1.5")
print("Step 3: loaded", flush=True)

v = m.encode("test")
print(f"Step 4: encoded, shape={v.shape}", flush=True)
print("DONE", flush=True)
