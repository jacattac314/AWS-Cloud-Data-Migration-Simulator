"""Unit tests for the KLO (Knowledge-Led Operations) service."""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models.database import Base, KnowledgeEntry
from backend.services.klo_service import (
    _cosine_similarity,
    _split_into_chunks,
    _tfidf_embed,
    get_embeddings,
    ingest_text,
    semantic_search,
    generate_answer,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ─── Text Chunking ────────────────────────────────────────────────────────────

class TestSplitChunks:
    def test_short_text_single_chunk(self):
        text = "This is a short sentence."
        chunks = _split_into_chunks(text, chunk_size=100, overlap=10)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_multiple_chunks(self):
        words = ["word"] * 1000
        text = " ".join(words)
        chunks = _split_into_chunks(text, chunk_size=100, overlap=10)
        assert len(chunks) > 1

    def test_overlap_content(self):
        words = list(f"word{i}" for i in range(200))
        text = " ".join(words)
        chunks = _split_into_chunks(text, chunk_size=100, overlap=20)
        # Last words of chunk[0] should appear at start of chunk[1]
        end_of_first = chunks[0].split()[-20:]
        start_of_second = chunks[1].split()[:20]
        assert end_of_first == start_of_second

    def test_empty_text_empty_list(self):
        chunks = _split_into_chunks("", chunk_size=100)
        assert chunks == []


# ─── TF-IDF Embedding ─────────────────────────────────────────────────────────

class TestTfidfEmbed:
    def test_returns_correct_count(self):
        texts = ["hello world", "migration runbook", "compliance itar"]
        embeddings, vocab = _tfidf_embed(texts)
        assert len(embeddings) == 3

    def test_embedding_is_list_of_floats(self):
        texts = ["hello world"]
        embeddings, _ = _tfidf_embed(texts)
        assert isinstance(embeddings[0], list)
        assert all(isinstance(v, float) for v in embeddings[0])

    def test_embeddings_l2_normalized(self):
        import math
        texts = ["hello world", "foo bar baz"]
        embeddings, _ = _tfidf_embed(texts)
        for emb in embeddings:
            norm = math.sqrt(sum(v ** 2 for v in emb))
            assert abs(norm - 1.0) < 1e-4 or norm < 1e-5  # normalized or zero vector

    def test_different_texts_different_embeddings(self):
        texts = ["AWS migration rehost", "ITAR compliance govcloud"]
        embeddings, _ = _tfidf_embed(texts)
        assert embeddings[0] != embeddings[1]

    def test_same_text_same_embedding(self):
        texts = ["identical text identical text", "identical text identical text"]
        embeddings, _ = _tfidf_embed(texts)
        assert embeddings[0] == embeddings[1]


# ─── Cosine Similarity ────────────────────────────────────────────────────────

class TestCosineSimilarity:
    def test_identical_vectors_score_1(self):
        v = [1.0, 0.5, 0.2]
        score = _cosine_similarity(v, v)
        assert abs(score - 1.0) < 1e-5

    def test_orthogonal_vectors_score_0(self):
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]
        score = _cosine_similarity(v1, v2)
        assert abs(score) < 1e-5

    def test_score_bounded_0_to_1(self):
        import random
        for _ in range(10):
            v1 = [random.random() for _ in range(50)]
            v2 = [random.random() for _ in range(50)]
            score = _cosine_similarity(v1, v2)
            assert -1.01 <= score <= 1.01

    def test_zero_vector_no_crash(self):
        v1 = [0.0] * 5
        v2 = [1.0] * 5
        score = _cosine_similarity(v1, v2)
        assert score == 0.0


# ─── Text Ingestion ───────────────────────────────────────────────────────────

class TestIngestText:
    def test_creates_entries(self, db):
        entries = ingest_text(db, "Hello world test content.", "Test Doc")
        assert len(entries) > 0
        assert all(isinstance(e, KnowledgeEntry) for e in entries)

    def test_entries_persisted(self, db):
        ingest_text(db, "Short content.", "My Doc", "myfile.txt")
        saved = db.query(KnowledgeEntry).all()
        assert len(saved) > 0

    def test_embedding_stored(self, db):
        entries = ingest_text(db, "Migration runbook content.", "Test")
        for entry in entries:
            assert entry.embedding_json is not None
            vec = json.loads(entry.embedding_json)
            assert isinstance(vec, list)
            assert len(vec) > 0

    def test_source_file_stored(self, db):
        ingest_text(db, "Content", "Title", source_file="ops_guide.txt")
        entry = db.query(KnowledgeEntry).first()
        assert entry.source_file == "ops_guide.txt"

    def test_entry_type_stored(self, db):
        ingest_text(db, "FAQ content", "FAQ Doc", entry_type="FAQ")
        entry = db.query(KnowledgeEntry).first()
        assert entry.entry_type == "FAQ"

    def test_multiple_chunks(self, db):
        long_text = " ".join(["word"] * 1000)
        entries = ingest_text(db, long_text, "Long Doc", chunk_size=100, overlap=10)
        assert len(entries) > 1


# ─── Semantic Search ─────────────────────────────────────────────────────────

class TestSemanticSearch:
    def test_empty_db_returns_empty(self, db):
        results = semantic_search(db, "migration runbook")
        assert results == []

    def test_returns_matching_entries(self, db):
        ingest_text(db, "EC2 instance migration procedure step by step", "EC2 Runbook")
        ingest_text(db, "Compliance ITAR requirements GovCloud", "ITAR Guide")
        results = semantic_search(db, "EC2 migration steps", top_k=2)
        assert len(results) > 0

    def test_top_k_respected(self, db):
        for i in range(10):
            ingest_text(db, f"Document {i} content about migration", f"Doc {i}")
        results = semantic_search(db, "migration", top_k=3)
        assert len(results) <= 3

    def test_results_have_score(self, db):
        ingest_text(db, "AWS rehost migration procedure", "Runbook")
        results = semantic_search(db, "rehost migration", top_k=1)
        for entry, score in results:
            assert isinstance(score, float)

    def test_results_ordered_by_relevance(self, db):
        ingest_text(db, "ITAR compliance govcloud encryption audit trail", "ITAR Doc")
        ingest_text(db, "Kitchen recipe pasta sauce tomato", "Unrelated Doc")
        results = semantic_search(db, "ITAR compliance govcloud", top_k=2)
        if len(results) >= 2:
            assert results[0][1] >= results[1][1]


# ─── Answer Generation (No API Key Fallback) ─────────────────────────────────

class TestGenerateAnswer:
    def test_no_api_key_returns_fallback(self, monkeypatch):
        monkeypatch.setattr("backend.services.klo_service.settings.OPENAI_API_KEY", "")
        chunks = ["This migration runbook explains EC2 rehost steps."]
        answer = generate_answer("How do I migrate EC2?", chunks)
        assert isinstance(answer, str)
        assert len(answer) > 10

    def test_returns_string(self, monkeypatch):
        monkeypatch.setattr("backend.services.klo_service.settings.OPENAI_API_KEY", "")
        answer = generate_answer("What is ITAR?", ["ITAR requires GovCloud deployment."])
        assert isinstance(answer, str)
