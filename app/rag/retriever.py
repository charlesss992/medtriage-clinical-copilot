import json
from pathlib import Path
from typing import List
import numpy as np
from openai import OpenAI, OpenAIError
from app.core.config import settings
from app.rag.ingest import _local_hash_embedding
from app.schemas.triage_schema import Citation

VECTOR_STORE_FILE = Path(settings.chroma_persist_dir) / "sop_vectors.json"


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _embed_query(query: str, target_dim: int, store_backend: str) -> np.ndarray:
    if store_backend == "openai" and settings.openai_api_key:
        try:
            client = OpenAI(api_key=settings.openai_api_key)
            raw = (
                client.embeddings.create(model=settings.embedding_model, input=[query])
                .data[0]
                .embedding
            )
            vec = np.array(raw, dtype=np.float32)
            if vec.shape[0] == target_dim:
                return vec
        except OpenAIError:
            pass
    return np.array(_local_hash_embedding(query, dim=target_dim), dtype=np.float32)


def retrieve_relevant_sops(query: str, top_k: int = 3) -> List[Citation]:
    if not VECTOR_STORE_FILE.exists():
        return []

    items = json.loads(VECTOR_STORE_FILE.read_text(encoding="utf-8"))
    if not items:
        return []

    first_vec = np.array(items[0]["embedding"], dtype=np.float32)
    target_dim = int(first_vec.shape[0])
    store_backend = items[0].get("backend", "local_hash")
    query_vec = _embed_query(query, target_dim=target_dim, store_backend=store_backend)

    scored = []
    for item in items:
        doc_vec = np.array(item["embedding"], dtype=np.float32)
        if doc_vec.shape[0] != target_dim:
            continue
        score = _cosine_similarity(query_vec, doc_vec)
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    citations: List[Citation] = []

    for _, item in scored[:top_k]:
        citations.append(
            Citation(
                document=item.get("document", "SOP Internal"),
                section=item.get("section", "Umum"),
                snippet=item.get("raw_text", "")[:280] + "...",
            )
        )
    return citations