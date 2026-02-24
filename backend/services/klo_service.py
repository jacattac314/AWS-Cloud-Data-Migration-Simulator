"""Knowledge-Led Operations (KLO) service.

Handles document ingestion, text chunking, embedding generation, and semantic search.
Uses OpenAI embeddings when an API key is configured; falls back to TF-IDF cosine
similarity for zero-dependency local operation.
"""

from __future__ import annotations

import json
import math
import re
from typing import List, Optional, Tuple

import numpy as np
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.database import AuditLog, KnowledgeEntry

# ─── Text Chunking ────────────────────────────────────────────────────────────

CHUNK_SIZE = 400    # tokens / words approximate
CHUNK_OVERLAP = 50


def _split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end == len(words):
            break
        start += chunk_size - overlap
    return chunks


# ─── Embedding Backends ──────────────────────────────────────────────────────

def _openai_embed(texts: List[str]) -> List[List[float]]:
    """Generate embeddings via OpenAI API (batched)."""
    import openai  # local import – only needed if API key present
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


def _tfidf_embed(texts: List[str], vocab: Optional[dict] = None) -> Tuple[List[List[float]], dict]:
    """
    Simple TF-IDF embedding fallback (no external dependencies beyond numpy).
    Returns (embeddings, vocab_dict).
    """
    # Build vocabulary
    tokenize = lambda t: re.findall(r"[a-z]+", t.lower())
    all_tokens = [tokenize(t) for t in texts]

    if vocab is None:
        all_words = sorted({w for tokens in all_tokens for w in tokens})
        vocab = {w: i for i, w in enumerate(all_words)}

    n = len(texts)
    vocab_size = len(vocab)
    tfidf_matrix = np.zeros((n, vocab_size), dtype=np.float32)

    # Document frequency
    df = np.zeros(vocab_size, dtype=np.float32)
    for tokens in all_tokens:
        unique = set(tokens)
        for w in unique:
            if w in vocab:
                df[vocab[w]] += 1

    idf = np.log((n + 1) / (df + 1)) + 1

    for i, tokens in enumerate(all_tokens):
        tf = np.zeros(vocab_size, dtype=np.float32)
        for w in tokens:
            if w in vocab:
                tf[vocab[w]] += 1
        if tf.sum() > 0:
            tf /= tf.sum()
        tfidf_matrix[i] = tf * idf

    # L2-normalize
    norms = np.linalg.norm(tfidf_matrix, axis=1, keepdims=True) + 1e-10
    tfidf_matrix /= norms

    return tfidf_matrix.tolist(), vocab


def get_embeddings(texts: List[str]) -> List[List[float]]:
    """Return embeddings for a list of texts, using OpenAI if available."""
    if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.startswith("sk-"):
        try:
            return _openai_embed(texts)
        except Exception:
            pass  # fall through to TF-IDF
    embeddings, _ = _tfidf_embed(texts)
    return embeddings


def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
    a, b = np.array(v1, dtype=np.float32), np.array(v2, dtype=np.float32)
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-10
    return float(np.dot(a, b) / denom)


# ─── Ingestion ────────────────────────────────────────────────────────────────

def ingest_text(
    db: Session,
    text: str,
    title: str,
    source_file: Optional[str] = None,
    entry_type: str = "Runbook",
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[KnowledgeEntry]:
    """Split text into chunks, embed, and persist KnowledgeEntry rows."""
    chunks = _split_into_chunks(text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        return []

    embeddings = get_embeddings(chunks)

    entries = []
    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        entry = KnowledgeEntry(
            title=f"{title} [chunk {idx + 1}]",
            content=chunk,
            source_file=source_file,
            entry_type=entry_type,
            chunk_index=idx,
            embedding_json=json.dumps(emb),
        )
        db.add(entry)
        entries.append(entry)

    db.commit()
    _audit(db, f"Ingested document '{title}' ({len(chunks)} chunks)", "KnowledgeEntry")
    return entries


def ingest_pdf(
    db: Session,
    pdf_bytes: bytes,
    title: str,
    source_file: Optional[str] = None,
) -> List[KnowledgeEntry]:
    """Extract text from a PDF and ingest it."""
    try:
        import pypdf
        reader = pypdf.PdfReader(__import__("io").BytesIO(pdf_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        raise ValueError(f"PDF extraction failed: {e}") from e
    return ingest_text(db, text, title, source_file or "upload.pdf")


# ─── Semantic Search ─────────────────────────────────────────────────────────

def semantic_search(
    db: Session,
    query: str,
    top_k: int = 5,
) -> List[Tuple[KnowledgeEntry, float]]:
    """
    Return the top-k knowledge entries most similar to *query*.
    Scores entries using cosine similarity of stored embeddings vs. query embedding.
    """
    entries = db.query(KnowledgeEntry).filter(KnowledgeEntry.embedding_json.isnot(None)).all()
    if not entries:
        return []

    # If TF-IDF fallback, we must re-embed using the stored corpus vocabulary
    # (for OpenAI this is a direct call)
    query_embs = get_embeddings([query])
    query_vec = query_embs[0]

    # Pad or truncate TF-IDF vectors to match query vector dimension
    q_len = len(query_vec)
    scored: List[Tuple[float, KnowledgeEntry]] = []
    for entry in entries:
        try:
            stored_vec = json.loads(entry.embedding_json)
        except (json.JSONDecodeError, TypeError):
            continue
        # Align dimensions (TF-IDF vocab may differ from query)
        e_len = len(stored_vec)
        if e_len != q_len:
            min_len = min(e_len, q_len)
            stored_vec = stored_vec[:min_len]
            query_vec_trimmed = query_vec[:min_len]
        else:
            query_vec_trimmed = query_vec
        score = _cosine_similarity(query_vec_trimmed, stored_vec)
        scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [(entry, score) for score, entry in scored[:top_k]]


# ─── AI Answer Generation ─────────────────────────────────────────────────────

def generate_answer(query: str, context_chunks: List[str]) -> str:
    """
    Use GPT to synthesize an answer from retrieved context.
    Falls back to a simple snippet if no OpenAI key is configured.
    """
    if not (settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.startswith("sk-")):
        # Fallback: return first relevant sentence from context
        for chunk in context_chunks:
            sentences = [s.strip() for s in chunk.split(".") if s.strip()]
            for s in sentences:
                if any(w in s.lower() for w in query.lower().split()):
                    return f"[No AI key – excerpt] {s}."
        return "[No AI key configured – showing raw excerpt]\n\n" + "\n\n".join(context_chunks[:2])

    import openai
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    context = "\n\n---\n\n".join(context_chunks)
    system_prompt = (
        "You are an expert cloud operations assistant for the Cloud Migration Command Center. "
        "Answer the user's question using only the provided context. "
        "Be concise and precise. If the answer is not in the context, say so."
    )
    response = client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
        ],
        max_tokens=600,
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


def generate_runbook(topic: str, context_chunks: List[str]) -> str:
    """Auto-generate a structured runbook entry from retrieved knowledge."""
    if not (settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.startswith("sk-")):
        return (
            f"# Runbook: {topic}\n\n"
            "## Overview\n[Auto-generated – configure OpenAI key for AI content]\n\n"
            "## Steps\n1. Step one\n2. Step two\n3. Verify\n\n"
            "## Rollback\n1. Reverse step 2\n2. Reverse step 1\n"
        )

    import openai
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    context = "\n\n".join(context_chunks)
    prompt = (
        f"Using the following operational documentation, generate a concise runbook for: '{topic}'.\n\n"
        f"Documentation:\n{context}\n\n"
        "Format the runbook as markdown with sections: Overview, Prerequisites, Steps, Verification, Rollback."
    )
    response = client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def _audit(db: Session, action: str, resource_type: str = ""):
    log = AuditLog(action=action, resource_type=resource_type)
    db.add(log)
    db.commit()
