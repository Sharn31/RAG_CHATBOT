"""Vector store service backed by ChromaDB.

Exposes:
    get_vector_store() -> ChromaVectorStore
        .create_session_collection(session_id, chunks, embeddings)
        .query_session(session_id, query_embedding, top_k) -> List[{"text","page","distance"}]
        .delete_session(session_id)

Kept as a thin class (rather than bare module functions) so `rag_service.py`
can depend on a swappable object - convenient for tests (see tests/test_chat.py,
which substitutes a fake store) and leaves room to add another backend later
without touching callers.
"""

import os
from typing import List, Dict
import numpy as np

from app.config import settings

_chroma_client = None


def _get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        import chromadb
        os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
    return _chroma_client


def _collection_name(session_id: str) -> str:
    return f"session_{session_id}"


class ChromaVectorStore:
    def create_session_collection(self, session_id: str, chunks: List[Dict], embeddings: np.ndarray) -> None:
        client = _get_chroma_client()
        name = _collection_name(session_id)
        try:
            client.delete_collection(name)
        except Exception:
            pass
        collection = client.create_collection(name=name, metadata={"hnsw:space": "cosine"})

        ids = [f"{session_id}_{i}" for i in range(len(chunks))]
        texts = [c["text"] for c in chunks]
        metadatas = [{"page": c["page"]} for c in chunks]
        embeddings_list = embeddings.tolist()

        batch_size = 100
        for start in range(0, len(ids), batch_size):
            end = start + batch_size
            collection.add(
                ids=ids[start:end],
                embeddings=embeddings_list[start:end],
                documents=texts[start:end],
                metadatas=metadatas[start:end],
            )

    def query_session(self, session_id: str, query_embedding: np.ndarray, top_k: int) -> List[Dict]:
        client = _get_chroma_client()
        try:
            collection = client.get_collection(_collection_name(session_id))
        except Exception:
            return []

        results = collection.query(query_embeddings=[query_embedding.tolist()], n_results=top_k)
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        return [
            {"text": doc, "page": meta.get("page"), "distance": dist}
            for doc, meta, dist in zip(docs, metas, distances)
        ]

    def delete_session(self, session_id: str) -> None:
        client = _get_chroma_client()
        try:
            client.delete_collection(_collection_name(session_id))
        except Exception:
            pass


_store_instance = None


def get_vector_store() -> ChromaVectorStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = ChromaVectorStore()
    return _store_instance
