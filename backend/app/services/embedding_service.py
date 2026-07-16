"""Wraps the sentence-transformers embedding model, plus a pickle cache
under data/embeddings/ so re-processing the same session is inspectable/reusable.
"""
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import pickle
from typing import List
import numpy as np

from app.config import settings

_model = None


def get_model():
    """Lazily loads the embedding model once per process (avoids pulling in
    sentence-transformers/torch just to import this module).
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _model


def embed_texts(texts: List[str]) -> np.ndarray:
    model = get_model()
    return model.encode(texts, show_progress_bar=False, convert_to_numpy=True)


def embed_query(query: str) -> np.ndarray:
    return embed_texts([query])[0]


def cache_embeddings(session_id: str, embeddings: np.ndarray) -> None:
    os.makedirs(settings.EMBEDDINGS_CACHE_DIR, exist_ok=True)
    path = os.path.join(settings.EMBEDDINGS_CACHE_DIR, f"{session_id}.pkl")
    with open(path, "wb") as f:
        pickle.dump(embeddings, f)


def load_cached_embeddings(session_id: str) -> np.ndarray:
    path = os.path.join(settings.EMBEDDINGS_CACHE_DIR, f"{session_id}.pkl")
    with open(path, "rb") as f:
        return pickle.load(f)
