"""Knowledge-Led Operations (KLO) API routes."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from backend.models.database import KnowledgeEntry, get_db
from backend.models.schemas import (
    KnowledgeCreate, KnowledgeResponse,
    KnowledgeSearchRequest, KnowledgeSearchResponse, KnowledgeSearchResult,
)
from backend.services.klo_service import (
    generate_answer, generate_runbook, ingest_pdf, ingest_text, semantic_search,
)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base (KLO)"])


@router.get("/entries", response_model=List[KnowledgeResponse])
def list_entries(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return db.query(KnowledgeEntry).offset(skip).limit(limit).all()


@router.post("/entries", response_model=List[KnowledgeResponse], status_code=201)
def create_entry(payload: KnowledgeCreate, db: Session = Depends(get_db)):
    """Manually add and embed a knowledge entry."""
    entries = ingest_text(
        db,
        payload.content,
        payload.title,
        payload.source_file,
        payload.entry_type or "Runbook",
    )
    return entries


@router.post("/upload/text", response_model=List[KnowledgeResponse], status_code=201)
async def upload_text_file(
    title: str,
    entry_type: str = "Runbook",
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a plain-text (.txt) file for ingestion into the knowledge base."""
    if not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are accepted on this endpoint.")
    content = (await file.read()).decode("utf-8", errors="replace")
    entries = ingest_text(db, content, title, file.filename, entry_type)
    return entries


@router.post("/upload/pdf", response_model=List[KnowledgeResponse], status_code=201)
async def upload_pdf_file(
    title: str,
    entry_type: str = "Runbook",
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a PDF for ingestion into the knowledge base."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted on this endpoint.")
    content = await file.read()
    try:
        entries = ingest_pdf(db, content, title, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return entries


@router.post("/search", response_model=KnowledgeSearchResponse)
def search_knowledge(payload: KnowledgeSearchRequest, db: Session = Depends(get_db)):
    """Semantic search over the knowledge base, optionally with AI-generated answer."""
    results_raw = semantic_search(db, payload.query, top_k=payload.top_k)
    if not results_raw:
        return KnowledgeSearchResponse(query=payload.query, results=[], answer=None)

    context_chunks = [entry.content for entry, _ in results_raw]
    answer = generate_answer(payload.query, context_chunks[:3])

    results = []
    for entry, score in results_raw:
        excerpt = entry.content[:300] + ("..." if len(entry.content) > 300 else "")
        results.append(
            KnowledgeSearchResult(
                entry=KnowledgeResponse(
                    id=entry.id,
                    title=entry.title,
                    content=entry.content,
                    source_file=entry.source_file,
                    entry_type=entry.entry_type,
                    chunk_index=entry.chunk_index,
                    created_at=entry.created_at,
                ),
                score=round(score, 4),
                excerpt=excerpt,
            )
        )

    return KnowledgeSearchResponse(query=payload.query, results=results, answer=answer)


@router.post("/generate/runbook")
def generate_runbook_entry(topic: str, top_k: int = 3, db: Session = Depends(get_db)):
    """Auto-generate a formatted runbook based on relevant knowledge entries."""
    results_raw = semantic_search(db, topic, top_k=top_k)
    context_chunks = [entry.content for entry, _ in results_raw]
    runbook = generate_runbook(topic, context_chunks)
    return {"topic": topic, "runbook": runbook}


@router.delete("/entries/{entry_id}", status_code=204)
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(KnowledgeEntry).filter(KnowledgeEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(entry)
    db.commit()


@router.delete("/entries", status_code=204)
def clear_all_entries(db: Session = Depends(get_db)):
    """Delete all knowledge entries (useful for demo resets)."""
    db.query(KnowledgeEntry).delete()
    db.commit()
