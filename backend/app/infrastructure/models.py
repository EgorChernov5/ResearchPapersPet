import uuid
from datetime import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
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
