import uuid
from datetime import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


# Project-specific persistence models keep research configuration and annotations local.
class ResearchProjectModel(Base):
    """
    Хранит исследовательский проект и его конфигурацию.

    Attributes:
        id (uuid.UUID): Внутренний идентификатор проекта.
        name (str): Пользовательское имя проекта.
        config (dict): Сериализованная конфигурация исследования.

    Fallbacks:
        Пустая конфигурация заменяется значениями доменного ResearchConfig в application layer.
    """

    __tablename__ = "research_projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False
    )


class ResearchQuestionModel(Base):
    """
    Хранит отдельный вопрос исследовательского проекта.

    Attributes:
        id (uuid.UUID): Идентификатор вопроса.
        project_id (uuid.UUID): Идентификатор проекта.
        text (str): Текст вопроса.

    Fallbacks:
        Пустой текст запрещается application validation.
    """

    __tablename__ = "research_questions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)


class RelatedWorkEntryModel(Base):
    """
    Хранит исходную строку Related Work и researcher annotations.

    Attributes:
        project_id (uuid.UUID): Идентификатор проекта.
        local_id (str): Идентификатор строки во входном файле.
        title (str): Название seed paper.

    Fallbacks:
        Необязательные аннотации сохраняются как NULL.
    """

    __tablename__ = "related_work_entries"
    __table_args__ = (UniqueConstraint("project_id", "local_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    local_id: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(Text)
    venue: Mapped[str | None] = mapped_column(String(255))
    bibtex_key: Mapped[str | None] = mapped_column(String(255))
    literature_block: Mapped[str | None] = mapped_column(Text)
    task: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str | None] = mapped_column(Text)
    datasets: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[str | None] = mapped_column(Text)
    code_available: Mapped[str | None] = mapped_column(String(100))
    data_available: Mapped[str | None] = mapped_column(String(100))
    usefulness: Mapped[str | None] = mapped_column(Text)
    comparison_ideas: Mapped[str | None] = mapped_column(Text)


# Global scientific models are shared by every research project.
class PaperModel(Base):
    """
    Хранит каноническую глобальную научную статью.

    Attributes:
        id (uuid.UUID): Внутренний идентификатор статьи.
        semantic_scholar_id (str | None): Канонический ID Semantic Scholar.
        title (str): Название статьи.

    Fallbacks:
        Неполные provider metadata сохраняются как NULL или пустой JSON-массив.
    """

    __tablename__ = "papers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    semantic_scholar_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    citation_count: Mapped[int | None] = mapped_column(Integer)
    influential_citation_count: Mapped[int | None] = mapped_column(Integer)
    reference_count: Mapped[int | None] = mapped_column(Integer)
    authors: Mapped[list] = mapped_column(JSON, nullable=False)
    categories: Mapped[list] = mapped_column(JSON, nullable=False)
    pdf_url: Mapped[str | None] = mapped_column(Text)


class ExternalIdentifierModel(Base):
    """
    Хранит provider-specific identifier глобальной статьи.

    Attributes:
        paper_id (uuid.UUID): Идентификатор глобальной статьи.
        provider (str): Нормализованное имя provider.
        value (str): Значение внешнего identifier.

    Fallbacks:
        Неизвестные identifiers не создают запись.
    """

    __tablename__ = "external_identifiers"
    __table_args__ = (
        UniqueConstraint("provider", "value"),
        UniqueConstraint("paper_id", "provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)


class CitationModel(Base):
    """
    Хранит уникальное направленное ребро source cites target.

    Attributes:
        source_paper_id (uuid.UUID): Цитирующая статья.
        target_paper_id (uuid.UUID): Цитируемая статья.

    Fallbacks:
        Рёбра без обеих статей не могут быть сохранены ограничениями БД.
    """

    __tablename__ = "citations"
    __table_args__ = (UniqueConstraint("source_paper_id", "target_paper_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )


# Project-paper rows hold all project-specific discovery and ranking state.
class ProjectPaperModel(Base):
    """
    Связывает глобальную статью с проектом и будущими scores.

    Attributes:
        project_id (uuid.UUID): Идентификатор проекта.
        paper_id (uuid.UUID): Идентификатор глобальной статьи.
        is_seed (bool): Признак исходной seed paper.

    Fallbacks:
        Scores остаются NULL до соответствующего pipeline stage.
    """

    __tablename__ = "project_papers"
    __table_args__ = (UniqueConstraint("project_id", "paper_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_seed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    depth: Mapped[int | None] = mapped_column(Integer)
    query_similarity: Mapped[float | None] = mapped_column(Float)
    seed_similarity: Mapped[float | None] = mapped_column(Float)
    topic_score: Mapped[float | None] = mapped_column(Float)
    citation_score: Mapped[float | None] = mapped_column(Float)
    recency_score: Mapped[float | None] = mapped_column(Float)
    impact_score: Mapped[float | None] = mapped_column(Float)
    distance_score: Mapped[float | None] = mapped_column(Float)
    connectivity_score: Mapped[float | None] = mapped_column(Float)
    pagerank_score: Mapped[float | None] = mapped_column(Float)
    graph_score: Mapped[float | None] = mapped_column(Float)
    final_score: Mapped[float | None] = mapped_column(Float)


class ResearchJobModel(Base):
    """
    Хранит состояние фонового research job.

    Attributes:
        id (uuid.UUID): Идентификатор job.
        status (str): Текущий pipeline status.
        progress (float): Доля выполненной работы от 0 до 1.

    Fallbacks:
        Необработанная ошибка переводит job в FAILED с error_message.
    """

    __tablename__ = "research_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    papers_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    papers_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Paper-level vectors are global and reusable across research projects.
class PaperEmbeddingModel(Base):
    """
    Хранит versioned paper-level embedding в PostgreSQL pgvector.

    Attributes:
        paper_id (uuid.UUID): Идентификатор global Paper.
        model_name (str): Имя embedding model.
        model_version (str): Версия model configuration.

    Fallbacks:
        Unique constraint не допускает duplicate embedding одной версии.
    """

    __tablename__ = "paper_embeddings"
    __table_args__ = (UniqueConstraint("paper_id", "model_name", "model_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(768), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False
    )


# Per-question semantic scores preserve relevance before project-level aggregation.
class ProjectPaperQuestionScoreModel(Base):
    """
    Хранит semantic score пары paper × research question.

    Attributes:
        project_id (uuid.UUID): Идентификатор проекта.
        paper_id (uuid.UUID): Идентификатор global Paper.
        question_id (uuid.UUID): Идентификатор research question.

    Fallbacks:
        Unique constraint делает repeated scoring idempotent.
    """

    __tablename__ = "project_paper_question_scores"
    __table_args__ = (UniqueConstraint("project_id", "paper_id", "question_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query_similarity: Mapped[float | None] = mapped_column(Float)
    topic_score: Mapped[float | None] = mapped_column(Float)


# Document artifacts are global to papers, while processing jobs retain project ownership.
class PaperDocumentModel(Base):
    """
    Хранит versioned PDF metadata глобальной статьи.

    Attributes:
        paper_id (uuid.UUID): Идентификатор global Paper.
        source (str): Источник документа.
        version (int): Монотонная версия PDF.

    Fallbacks:
        Storage metadata остаются NULL до успешной загрузки.
    """

    __tablename__ = "paper_documents"
    __table_args__ = (
        UniqueConstraint("paper_id", "source", "version"),
        Index(
            "uq_paper_documents_active_source",
            "paper_id",
            "source",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
        CheckConstraint("version > 0", name="ck_paper_documents_positive_version"),
        CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="ck_paper_documents_non_negative_size",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(Text)
    checksum: Mapped[str | None] = mapped_column(String(128))
    media_type: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False
    )


class DocumentProcessingJobModel(Base):
    """
    Хранит project-scoped lifecycle одного PDF target.

    Attributes:
        project_id (uuid.UUID): Проект-владелец target.
        paper_id (uuid.UUID): Глобальная Paper target.
        status (str): Текущее состояние document pipeline.

    Fallbacks:
        document_id остаётся NULL до появления versioned PDF.
    """

    __tablename__ = "document_processing_jobs"
    __table_args__ = (UniqueConstraint("project_id", "paper_id", "source"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    research_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="SET NULL"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("paper_documents.id", ondelete="SET NULL"), index=True
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False
    )


class ParsedDocumentModel(Base):
    """
    Хранит versioned parser result и ссылку на исходный TEI.

    Attributes:
        document_id (uuid.UUID): Исходная версия PDF.
        parser_name (str): Имя parser.
        parser_version (str): Версия parser/config.

    Fallbacks:
        Ошибка parsing сохраняется без создания dependent elements.
    """

    __tablename__ = "parsed_documents"
    __table_args__ = (UniqueConstraint("document_id", "parser_name", "parser_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("paper_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parser_name: Mapped[str] = mapped_column(String(100), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(100), nullable=False)
    tei_storage_key: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentElementModel(Base):
    """
    Хранит канонически упорядоченный элемент parsed document.

    Attributes:
        parsed_document_id (uuid.UUID): Версия parsed document.
        element_type (str): Нормализованный structural type.
        position (int): Позиция элемента в документе.

    Fallbacks:
        Необязательные TEI metadata сохраняются как NULL.
    """

    __tablename__ = "document_elements"
    __table_args__ = (
        UniqueConstraint("parsed_document_id", "position"),
        CheckConstraint("position >= 0", name="ck_document_elements_non_negative_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    parsed_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parsed_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    element_type: Mapped[str] = mapped_column(String(50), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    section_path: Mapped[list | None] = mapped_column(JSON)
    page_number: Mapped[int | None] = mapped_column(Integer)
    coordinates: Mapped[dict | None] = mapped_column(JSON)


class CitationMarkerModel(Base):
    """
    Связывает in-text citation marker с bibliography element.

    Attributes:
        marker_element_id (uuid.UUID): Элемент с marker.
        bibliography_element_id (uuid.UUID): Bibliography target.

    Fallbacks:
        Удаление любого элемента каскадно удаляет связь.
    """

    __tablename__ = "citation_markers"
    __table_args__ = (UniqueConstraint("marker_element_id", "bibliography_element_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    marker_element_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_elements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bibliography_element_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_elements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    marker_text: Mapped[str] = mapped_column(Text, nullable=False)


class PaperChunkModel(Base):
    """
    Хранит versioned token chunk как PostgreSQL source of truth.

    Attributes:
        stable_id (str): Детерминированный ID для vector index.
        chunk_index (int): Позиция chunk в versioned наборе.
        chunker_version (str): Версия chunking policy.

    Fallbacks:
        Structural metadata остаются NULL, если parser их не предоставил.
    """

    __tablename__ = "paper_chunks"
    __table_args__ = (
        UniqueConstraint("stable_id"),
        UniqueConstraint("parsed_document_id", "chunker_version", "chunk_index"),
        Index(
            "uq_paper_chunks_active_position",
            "parsed_document_id",
            "chunk_index",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
        CheckConstraint("chunk_index >= 0", name="ck_paper_chunks_non_negative_index"),
        CheckConstraint(
            "token_start >= 0 AND token_end >= token_start",
            name="ck_paper_chunks_token_offsets",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    parsed_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parsed_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    element_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_elements.id", ondelete="SET NULL"), index=True
    )
    stable_id: Mapped[str] = mapped_column(String(255), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_start: Mapped[int] = mapped_column(Integer, nullable=False)
    token_end: Mapped[int] = mapped_column(Integer, nullable=False)
    section_path: Mapped[list | None] = mapped_column(JSON)
    page_number: Mapped[int | None] = mapped_column(Integer)
    coordinates: Mapped[dict | None] = mapped_column(JSON)
    chunker_version: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
