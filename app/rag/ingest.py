import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List
import numpy as np
from openai import OpenAI, OpenAIError
from pypdf import PdfReader
from app.core.config import settings

VECTOR_STORE_FILE = Path(settings.chroma_persist_dir) / "sop_vectors.json"
LOCAL_DIM = 384


def _local_hash_embedding(text: str, dim: int = LOCAL_DIM) -> List[float]:
    """Embedding lokal gratis berbasis token + character n-gram hashing."""
    vec = np.zeros(dim, dtype=np.float32)
    clean = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    tokens = clean.split()
    features = list(tokens)
    for tok in tokens:
        if len(tok) >= 3:
            features.extend(tok[i : i + 3] for i in range(len(tok) - 2))

    if not features:
        return vec.tolist()

    for feat in features:
        digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if (digest[4] % 2 == 0) else -1.0
        vec[idx] += sign

    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec.tolist()


def parse_markdown_sections(file_path: Path) -> List[Dict]:
    content = file_path.read_text(encoding="utf-8")
    chunks: List[Dict] = []
    current_doc_title = file_path.name
    current_section = "Umum"
    buffer: List[str] = []

    for line in content.splitlines():
        if line.startswith("# "):
            if buffer:
                chunks.append({
                    "document": current_doc_title,
                    "section": current_section,
                    "text": "\n".join(buffer).strip(),
                })
                buffer = []
            current_doc_title = line.replace("# ", "").strip()
        elif line.startswith("## "):
            if buffer:
                chunks.append({
                    "document": current_doc_title,
                    "section": current_section,
                    "text": "\n".join(buffer).strip(),
                })
                buffer = []
            current_section = line.replace("## ", "").strip()
        else:
            if line.strip():
                buffer.append(line.strip())

    if buffer:
        chunks.append({
            "document": current_doc_title,
            "section": current_section,
            "text": "\n".join(buffer).strip(),
        })
    return [c for c in chunks if len(c["text"]) > 20]


def parse_pdf_pages(file_path: Path) -> List[Dict]:
    reader = PdfReader(str(file_path))
    chunks: List[Dict] = []
    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 30:
            chunks.append({
                "document": file_path.name,
                "section": f"Halaman {idx + 1}",
                "text": text,
            })
    return chunks


def _embed_texts(texts: List[str]) -> tuple[List[List[float]], str]:
    """Coba pakai OpenAI embeddings; jika gagal (kuota/key/jaringan), fallback ke lokal gratis."""
    if settings.openai_api_key and settings.openai_api_key.startswith("sk-"):
        try:
            client = OpenAI(api_key=settings.openai_api_key)
            resp = client.embeddings.create(model=settings.embedding_model, input=texts)
            vecs = [
                np.array(item.embedding, dtype=np.float32).tolist()
                for item in resp.data
            ]
            return vecs, "openai"
        except OpenAIError as exc:
            print(f"[INFO] OpenAI embedding unavailable ({exc}). Menggunakan embedding lokal gratis.")
    return [_local_hash_embedding(t) for t in texts], "local_hash"


def ingest_sops(sop_dir: str = "data/sops") -> int:
    all_chunks: List[Dict] = []

    for path in Path(sop_dir).glob("*"):
        if path.suffix.lower() == ".md":
            all_chunks.extend(parse_markdown_sections(path))
        elif path.suffix.lower() == ".pdf":
            all_chunks.extend(parse_pdf_pages(path))

    if not all_chunks:
        return 0

    texts = [f"{c['document']} - {c['section']}: {c['text']}" for c in all_chunks]
    vectors, backend = _embed_texts(texts)

    store_items = []
    for idx, chunk in enumerate(all_chunks):
        store_items.append({
            "id": f"sop_{idx}",
            "document": chunk["document"],
            "section": chunk["section"],
            "raw_text": chunk["text"],
            "embedding": vectors[idx],
            "backend": backend,
        })

    VECTOR_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    VECTOR_STORE_FILE.write_text(
        json.dumps(store_items, ensure_ascii=False), encoding="utf-8"
    )
    return len(store_items)


if __name__ == "__main__":
    count = ingest_sops()
    print(f"Berhasil mengindeks {count} bagian SOP klinis ke penyimpanan vektor lokal.")