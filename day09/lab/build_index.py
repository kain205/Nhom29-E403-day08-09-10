"""
build_index.py — Build ChromaDB index cho Day 09.

Dùng OpenAI text-embedding-3-small (khớp với workers/retrieval.py).

Chạy 1 lần trước khi test workers:
    python build_index.py
"""

import os
import chromadb
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

DOCS_DIR = "./data/docs"
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "day09_docs"
EMBED_MODEL = "text-embedding-3-small"
CHUNK_SIZE = 400
CHUNK_OVERLAP = 60


def chunk_text(text: str) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start : start + CHUNK_SIZE])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c for c in chunks if c.strip()]


def get_embeddings(texts: list[str], client: OpenAI) -> list[list[float]]:
    resp = client.embeddings.create(input=texts, model=EMBED_MODEL)
    return [item.embedding for item in resp.data]


def build():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY not found. Add it to .env")

    client = OpenAI(api_key=api_key)

    chroma = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        chroma.delete_collection(COLLECTION_NAME)
        print(f"Deleted existing '{COLLECTION_NAME}'")
    except Exception:
        pass
    col = chroma.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    total = 0
    for fname in sorted(os.listdir(DOCS_DIR)):
        fpath = os.path.join(DOCS_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        with open(fpath, encoding="utf-8") as f:
            content = f.read()

        chunks = chunk_text(content)
        embeddings = get_embeddings(chunks, client)

        col.add(
            documents=chunks,
            embeddings=embeddings,
            ids=[f"{fname}__{i}" for i in range(len(chunks))],
            metadatas=[{"source": fname, "chunk_index": i} for i in range(len(chunks))],
        )
        print(f"  {fname} -> {len(chunks)} chunks")
        total += len(chunks)

    print(f"\nTotal: {total} chunks | collection.count(): {col.count()}")

    # Sanity check
    q = get_embeddings(["SLA ticket P1"], client)[0]
    r = col.query(query_embeddings=[q], n_results=2,
                  include=["documents", "metadatas", "distances"])
    print("\nSanity check -- 'SLA ticket P1':")
    for doc, meta, d in zip(r["documents"][0], r["metadatas"][0], r["distances"][0]):
        print(f"  [{1-d:.3f}] {meta['source']}: {doc[:80]}...")
    print("\nIndex build complete.")


if __name__ == "__main__":
    build()
