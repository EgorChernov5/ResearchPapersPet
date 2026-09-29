from dataclasses import asdict
from uuid import uuid4

import pytest
from app.domain.document import (
    DocumentElement,
    DocumentElementType,
    DocumentJobStatus,
    DocumentSource,
    PaperChunk,
)
from app.domain.paper import ProviderPaper
from app.domain.project import ResearchConfig
from app.domain.research_job import ResearchJobStatus
from app.infrastructure.database import Base
from app.infrastructure.models import (
    DocumentProcessingJobModel,
    PaperChunkModel,
    PaperDocumentModel,
    ResearchJobModel,
    ResearchProjectModel,
)
from app.repositories.documents import DocumentJobRepository, DocumentRepository
from app.repositories.papers import PaperRepository
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def test_document_status_transitions_accept_only_adjacent_lifecycle_steps() -> None:
    """
    Проверяет допустимые и невозможные переходы document lifecycle.

    Returns:
        None: Assertions фиксируют state machine contract.

    Fallbacks:
        Terminal states не могут быть перезапущены неявным переходом.
    """

    # Validate the complete successful path and representative forbidden skips.
    assert DocumentJobStatus.PENDING.can_transition_to(DocumentJobStatus.DOWNLOADING)
    assert DocumentJobStatus.DOWNLOADING.can_transition_to(DocumentJobStatus.PARSING)
    assert DocumentJobStatus.PARSING.can_transition_to(DocumentJobStatus.CHUNKING)
    assert DocumentJobStatus.CHUNKING.can_transition_to(DocumentJobStatus.INDEXING)
    assert DocumentJobStatus.INDEXING.can_transition_to(DocumentJobStatus.COMPLETED)
    assert not DocumentJobStatus.PENDING.can_transition_to(DocumentJobStatus.COMPLETED)
    assert not DocumentJobStatus.COMPLETED.can_transition_to(DocumentJobStatus.PENDING)
    assert not DocumentJobStatus.UNAVAILABLE.can_transition_to(DocumentJobStatus.DOWNLOADING)


def test_document_job_repository_is_idempotent_and_validates_transitions() -> None:
    """
    Проверяет target idempotency и persistent state transition validation.

    Returns:
        None: Один project/paper/source создаёт ровно одну job.

    Fallbacks:
        Невозможный переход отклоняется до изменения строки.
    """

    # Persist the minimal parent graph for a project-owned PDF target.
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    project_id = uuid4()
    research_job_id = uuid4()
    with Session(engine) as session:
        session.add(
            ResearchProjectModel(
                id=project_id,
                name="Document project",
                config=asdict(ResearchConfig()),
            )
        )
        session.flush()
        paper = PaperRepository(session).upsert(
            ProviderPaper("document-paper", "Document Paper", {})
        )
        session.add(
            ResearchJobModel(
                id=research_job_id,
                project_id=project_id,
                status=ResearchJobStatus.COMPLETED.value,
                progress=1.0,
                papers_discovered=1,
                papers_processed=1,
            )
        )
        session.flush()

        # Repeated selection returns one target and transition validation remains strict.
        jobs = DocumentJobRepository(session)
        first = jobs.create_target(project_id, paper.id, research_job_id)
        repeated = jobs.create_target(project_id, paper.id, research_job_id)
        assert first.id == repeated.id
        assert jobs.update_status(first.id, DocumentJobStatus.DOWNLOADING).status == (
            DocumentJobStatus.DOWNLOADING
        )
        with pytest.raises(ValueError, match="Invalid document job transition"):
            jobs.update_status(first.id, DocumentJobStatus.COMPLETED)
        awaiting = jobs.update_status(first.id, DocumentJobStatus.AWAITING_UPLOAD)
        research_job = session.get(ResearchJobModel, research_job_id)
        assert awaiting.status == DocumentJobStatus.AWAITING_UPLOAD
        assert research_job.status == ResearchJobStatus.COMPLETED.value
        assert session.scalar(select(func.count()).select_from(DocumentProcessingJobModel)) == 1
    engine.dispose()


def test_document_versions_and_chunks_reject_duplicate_active_records() -> None:
    """
    Проверяет uniqueness active PDF и chunk versions.

    Returns:
        None: Database constraints отклоняют конфликтующие active records.

    Fallbacks:
        Repository checksum idempotency не заменяет database-level protection.
    """

    # Create one complete document ancestry using the real repositories.
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        paper = PaperRepository(session).upsert(
            ProviderPaper("versioned-paper", "Versioned Paper", {})
        )
        documents = DocumentRepository(session)
        document = documents.create_document(
            paper.id,
            DocumentSource.ARXIV,
            "papers/versioned/document.pdf",
            "checksum-one",
            "application/pdf",
            100,
        )
        repeated = documents.create_document(
            paper.id,
            DocumentSource.ARXIV,
            "papers/versioned/document.pdf",
            "checksum-one",
            "application/pdf",
            100,
        )
        assert document.id == repeated.id
        changed = documents.create_document(
            paper.id,
            DocumentSource.ARXIV,
            "papers/versioned/document-checksum-two.pdf",
            "checksum-two",
            "application/pdf",
            200,
        )
        assert changed.id != document.id
        assert changed.version == 2
        assert not session.get(PaperDocumentModel, document.id).is_active
        parsed = documents.create_parsed_document(document.id, "grobid", "1")
        element = documents.add_element(
            DocumentElement(
                parsed_document_id=parsed.id,
                element_type=DocumentElementType.PARAGRAPH,
                position=0,
                text="A paragraph.",
            )
        )
        documents.add_chunk(
            PaperChunk(
                parsed_document_id=parsed.id,
                element_id=element.id,
                stable_id="chunk-v1-0",
                chunk_index=0,
                text="A paragraph.",
                token_start=0,
                token_end=3,
                chunker_version="1",
                embedding_model="specter",
                embedding_version="1",
            )
        )
        session.commit()

        # A second active chunk at the same position conflicts even with another chunker version.
        session.add(
            PaperChunkModel(
                parsed_document_id=parsed.id,
                element_id=element.id,
                stable_id="chunk-v2-0",
                chunk_index=0,
                text="A paragraph.",
                token_start=0,
                token_end=3,
                chunker_version="2",
                embedding_model="specter",
                embedding_version="1",
                is_active=True,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

        # A direct duplicate active PDF proves the partial unique index is not repository-only.
        session.add(
            PaperDocumentModel(
                paper_id=paper.id,
                source=DocumentSource.ARXIV.value,
                version=3,
                storage_key="papers/versioned/duplicate.pdf",
                checksum="checksum-two",
                media_type="application/pdf",
                size_bytes=200,
                status=DocumentJobStatus.PARSING.value,
                is_active=True,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
    engine.dispose()
