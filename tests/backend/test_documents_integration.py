from dataclasses import asdict
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.config import Settings, settings
from app.domain.document import (
    CitationMarker,
    DocumentElement,
    DocumentElementType,
    DocumentJobStatus,
    DocumentSource,
    PaperChunk,
)
from app.domain.paper import ProviderPaper
from app.domain.project import ResearchConfig
from app.domain.research_job import ResearchJobStatus
from app.infrastructure.database import Database
from app.infrastructure.models import (
    CitationMarkerModel,
    DocumentElementModel,
    DocumentProcessingJobModel,
    PaperChunkModel,
    PaperDocumentModel,
    PaperModel,
    ParsedDocumentModel,
    ResearchJobModel,
    ResearchProjectModel,
)
from app.repositories.documents import DocumentJobRepository, DocumentRepository
from app.repositories.papers import PaperRepository
from sqlalchemy import create_engine, delete, func, inspect, select, text
from sqlalchemy.engine import make_url


@pytest.mark.service_integration
def test_alembic_upgrades_previous_revision_to_document_schema(monkeypatch) -> None:
    """
    Проверяет Alembic upgrade с предыдущей revision на реальном PostgreSQL.

    Parameters:
        monkeypatch (MonkeyPatch): Изолирует DATABASE_URL временной schema.

    Returns:
        None: Все document tables присутствуют после upgrade head.

    Fallbacks:
        Временная schema удаляется даже при migration failure.
    """

    # Create a dedicated PostgreSQL schema so migration testing never mutates application tables.
    base_url = make_url(Settings().database_url)
    schema = f"document_migration_{uuid4().hex}"
    admin_engine = create_engine(base_url)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        extension_schema = connection.scalar(
            text(
                "SELECT namespace.nspname "
                "FROM pg_extension AS extension "
                "JOIN pg_namespace AS namespace ON namespace.oid = extension.extnamespace "
                "WHERE extension.extname = 'vector'"
            )
        )
    if extension_schema is None:
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()
        pytest.fail("PostgreSQL pgvector extension is not installed")
    schema_url = base_url.set(
        query={
            **base_url.query,
            "options": f"-csearch_path={schema},{extension_schema}",
        }
    ).render_as_string(hide_password=False)

    try:
        # Run the exact previous revision first, then apply only the new document migration.
        monkeypatch.setenv("DATABASE_URL", schema_url)
        settings.cache_clear()
        alembic = Config("backend/alembic.ini")
        command.upgrade(alembic, "20260825_0002")
        command.upgrade(alembic, "head")

        # Inspect the isolated schema through the same search_path used by Alembic.
        migrated_engine = create_engine(schema_url)
        tables = set(inspect(migrated_engine).get_table_names())
        assert {
            "paper_documents",
            "document_processing_jobs",
            "parsed_documents",
            "document_elements",
            "citation_markers",
            "paper_chunks",
        } <= tables
        migrated_engine.dispose()
    finally:
        # Remove only the UUID-named schema owned by this test and restore cached settings.
        settings.cache_clear()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.mark.service_integration
def test_document_repository_cascades_without_orphans_on_postgresql() -> None:
    """
    Проверяет repository contracts и cascade policy на реальном PostgreSQL.

    Returns:
        None: Удаление Paper удаляет jobs, documents и все derived rows.

    Fallbacks:
        Test-owned project удаляется в finally при любом результате.
    """

    # Persist a complete document ownership tree under UUID-isolated parents.
    database = Database(Settings())
    project_id = uuid4()
    paper_id = None
    with database.session_factory() as session:
        session.add(
            ResearchProjectModel(
                id=project_id,
                name="Document cascade integration",
                config=asdict(ResearchConfig()),
            )
        )
        session.flush()
        paper = PaperRepository(session).upsert(
            ProviderPaper(f"document-{uuid4().hex}", "Document Cascade", {})
        )
        paper_id = paper.id
        research_job = ResearchJobModel(
            project_id=project_id,
            status=ResearchJobStatus.COMPLETED.value,
            progress=1.0,
            papers_discovered=1,
            papers_processed=1,
        )
        session.add(research_job)
        session.flush()
        job = DocumentJobRepository(session).create_target(
            project_id,
            paper.id,
            research_job.id,
        )
        documents = DocumentRepository(session)
        document = documents.create_document(
            paper.id,
            DocumentSource.ARXIV,
            f"papers/{paper.id}/document.pdf",
            uuid4().hex,
            "application/pdf",
            128,
        )
        DocumentJobRepository(session).update_status(
            job.id,
            DocumentJobStatus.DOWNLOADING,
        )
        DocumentJobRepository(session).update_status(
            job.id,
            DocumentJobStatus.PARSING,
            document.id,
        )
        parsed = documents.create_parsed_document(document.id, "grobid", "integration")
        paragraph = documents.add_element(
            DocumentElement(
                parsed_document_id=parsed.id,
                element_type=DocumentElementType.PARAGRAPH,
                position=0,
                text="Citation [1].",
            )
        )
        bibliography = documents.add_element(
            DocumentElement(
                parsed_document_id=parsed.id,
                element_type=DocumentElementType.BIBLIOGRAPHY,
                position=1,
                text="Reference one.",
            )
        )
        documents.add_citation_marker(CitationMarker(paragraph.id, bibliography.id, "[1]"))
        documents.add_chunk(
            PaperChunk(
                parsed_document_id=parsed.id,
                element_id=paragraph.id,
                stable_id=f"integration-{uuid4().hex}",
                chunk_index=0,
                text="Citation [1].",
                token_start=0,
                token_end=4,
                chunker_version="integration",
                embedding_model="specter",
                embedding_version="integration",
            )
        )
        session.commit()

    try:
        # Delete the global ownership root and verify every dependent table is empty for its IDs.
        with database.session_factory() as session:
            document_ids = set(
                session.scalars(
                    select(PaperDocumentModel.id).where(PaperDocumentModel.paper_id == paper_id)
                )
            )
            parsed_ids = set(
                session.scalars(
                    select(ParsedDocumentModel.id).where(
                        ParsedDocumentModel.document_id.in_(document_ids)
                    )
                )
            )
            element_ids = set(
                session.scalars(
                    select(DocumentElementModel.id).where(
                        DocumentElementModel.parsed_document_id.in_(parsed_ids)
                    )
                )
            )
            session.execute(delete(PaperModel).where(PaperModel.id == paper_id))
            session.commit()

        with database.session_factory() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ParsedDocumentModel)
                    .where(ParsedDocumentModel.id.in_(parsed_ids))
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(DocumentElementModel)
                    .where(DocumentElementModel.id.in_(element_ids))
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(CitationMarkerModel)
                    .where(
                        CitationMarkerModel.marker_element_id.in_(element_ids)
                        | CitationMarkerModel.bibliography_element_id.in_(element_ids)
                    )
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(PaperChunkModel)
                    .where(PaperChunkModel.parsed_document_id.in_(parsed_ids))
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(DocumentProcessingJobModel)
                    .where(DocumentProcessingJobModel.project_id == project_id)
                )
                == 0
            )
    finally:
        # Delete the remaining test project; its target job cascades with project ownership.
        with database.session_factory() as session:
            session.execute(
                delete(ResearchProjectModel).where(ResearchProjectModel.id == project_id)
            )
            session.commit()
        database.dispose()
