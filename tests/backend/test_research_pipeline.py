from dataclasses import asdict
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from app.domain.paper import ProviderPaper
from app.domain.project import ResearchConfig
from app.domain.research_job import ResearchJob, ResearchJobStatus
from app.infrastructure.database import Base
from app.infrastructure.models import (
    CitationModel,
    PaperEmbeddingModel,
    ProjectPaperModel,
    ProjectPaperQuestionScoreModel,
    RelatedWorkEntryModel,
    ResearchJobModel,
    ResearchProjectModel,
    ResearchQuestionModel,
)
from app.providers.base import ScholarlyProvider
from app.repositories.research_jobs import ResearchJobRepository
from app.research.embeddings import EmbeddingService
from app.research.pipeline import ResearchPipeline
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker


@pytest.mark.asyncio
async def test_pipeline_resolves_discovers_and_persists_depth_one() -> None:
    """
    Проверяет полный fixture-based pipeline текущего milestone.

    Returns:
        None: Assertions подтверждают COMPLETED job и persistent graph.

    Fallbacks:
        Mock provider исключает зависимость от live Semantic Scholar API.
    """

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    project_id = uuid4()
    question_id = uuid4()
    job_id = uuid4()
    config = ResearchConfig(max_depth=1, max_papers=10, top_k_expansion=5)
    with Session(engine) as session:
        session.add(
            ResearchProjectModel(
                id=project_id,
                name="Research",
                config=asdict(config),
            )
        )
        session.add(
            ResearchQuestionModel(
                id=question_id,
                project_id=project_id,
                text="Which papers are relevant to the seed topic?",
            )
        )
        session.add(
            RelatedWorkEntryModel(
                project_id=project_id,
                local_id="RW01",
                title="Seed Paper",
                year=2024,
                source="DOI:10.1000/seed",
            )
        )
        session.add(
            ResearchJobModel(
                id=job_id,
                project_id=project_id,
                status=ResearchJobStatus.PENDING.value,
                progress=0.0,
                papers_discovered=0,
                papers_processed=0,
            )
        )
        session.commit()

    seed = ProviderPaper(
        "seed",
        "Seed Paper",
        {"doi": "10.1000/seed"},
        year=2024,
        citation_count=100,
    )
    reference = ProviderPaper("reference", "Reference", {}, year=2023, citation_count=50)
    citing = ProviderPaper("citing", "Citing", {}, year=2025, citation_count=20)
    provider = Mock(spec=ScholarlyProvider)
    provider.get_paper = AsyncMock(return_value=seed)
    provider.search_papers = AsyncMock(return_value=[])
    provider.get_papers_batch = AsyncMock(return_value=[seed])
    provider.get_references = AsyncMock(return_value=[reference])
    provider.get_citations = AsyncMock(return_value=[citing])
    encoder = Mock()
    encoder.get_sentence_embedding_dimension.return_value = 768
    encoder.encode.side_effect = lambda texts, **kwargs: [[1.0] + [0.0] * 767 for _ in texts]
    embedding_service = EmbeddingService(
        model_name="fixture-model",
        model_version="1",
        dimensions=768,
        batch_size=4,
        encoder=encoder,
    )

    # Record every committed lifecycle transition while preserving repository behavior.
    observed_statuses = []
    original_update = ResearchJobRepository.update

    def recording_update(
        repository: ResearchJobRepository,
        current_job_id: UUID,
        status: ResearchJobStatus,
        progress: float,
        papers_discovered: int | None = None,
        papers_processed: int | None = None,
        error_message: str | None = None,
    ) -> ResearchJob:
        """
        Записывает промежуточный статус и делегирует обновление repository.

        Parameters:
            repository (ResearchJobRepository): Текущий repository.
            current_job_id (UUID): Идентификатор job.
            status (ResearchJobStatus): Новый статус.
            progress (float): Текущий прогресс.
            papers_discovered (int | None): Число найденных статей. По умолчанию: None.
            papers_processed (int | None): Число обработанных статей. По умолчанию: None.
            error_message (str | None): Диагностика ошибки. По умолчанию: None.

        Returns:
            ResearchJob: Сохранённое состояние job.

        Fallbacks:
            Исключения исходного repository передаются pipeline без изменений.
        """

        observed_statuses.append(status)
        return original_update(
            repository,
            current_job_id,
            status,
            progress,
            papers_discovered,
            papers_processed,
            error_message,
        )

    with patch.object(ResearchJobRepository, "update", new=recording_update):
        result = await ResearchPipeline(
            sessions,
            provider,
            embedding_service,
        ).run(project_id, job_id)

    with Session(engine) as session:
        assert result.status == ResearchJobStatus.COMPLETED
        assert session.get(ResearchJobModel, job_id).status == ResearchJobStatus.COMPLETED.value
        assert session.scalar(select(func.count()).select_from(ProjectPaperModel)) == 3
        assert session.scalar(select(func.count()).select_from(CitationModel)) == 2
        assert session.scalar(select(func.count()).select_from(PaperEmbeddingModel)) == 3
        assert session.scalar(select(func.count()).select_from(ProjectPaperQuestionScoreModel)) == 3
        depths = sorted(session.scalars(select(ProjectPaperModel.depth)).all())
        assert depths == [0, 1, 1]
        scores = session.scalars(select(ProjectPaperModel.topic_score)).all()
        assert scores == [1.0, 1.0, 1.0]
        ranking_rows = session.scalars(select(ProjectPaperModel)).all()
        assert all(row.citation_score is not None for row in ranking_rows)
        assert all(row.recency_score is not None for row in ranking_rows)
        assert all(row.pagerank_score is not None for row in ranking_rows)
        assert all(row.impact_score is not None for row in ranking_rows)
        assert all(row.graph_score is not None for row in ranking_rows)
        assert all(row.final_score is not None for row in ranking_rows)
        assert max(row.pagerank_score for row in ranking_rows) == pytest.approx(1.0)
        assert observed_statuses == [
            ResearchJobStatus.RESOLVING_SEEDS,
            ResearchJobStatus.DISCOVERING,
            ResearchJobStatus.DISCOVERING,
            ResearchJobStatus.EMBEDDING,
            ResearchJobStatus.SCORING,
            ResearchJobStatus.GRAPH_ANALYSIS,
            ResearchJobStatus.COMPLETED,
        ]
    engine.dispose()


@pytest.mark.asyncio
async def test_pipeline_marks_job_failed_when_no_seed_can_be_resolved() -> None:
    """
    Проверяет terminal FAILED при полном сбое seed resolution.

    Returns:
        None: Assertions подтверждают persisted error и отсутствие research данных.

    Fallbacks:
        Ошибка provider изолируется resolver, после чего pipeline формирует общую причину сбоя.
    """

    # Persist the minimum project input required to reach seed resolution.
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    project_id = uuid4()
    job_id = uuid4()
    with Session(engine) as session:
        session.add(
            ResearchProjectModel(
                id=project_id,
                name="Research",
                config=asdict(ResearchConfig()),
            )
        )
        session.add(
            RelatedWorkEntryModel(
                project_id=project_id,
                local_id="RW01",
                title="Missing Paper",
                year=2024,
                source=None,
            )
        )
        session.add(
            ResearchJobModel(
                id=job_id,
                project_id=project_id,
                status=ResearchJobStatus.PENDING.value,
                progress=0.0,
                papers_discovered=0,
                papers_processed=0,
            )
        )
        session.commit()

    # Return no candidates from either title-search fallback.
    provider = Mock(spec=ScholarlyProvider)
    provider.search_papers = AsyncMock(return_value=[])
    embedding_service = Mock(spec=EmbeddingService)

    with pytest.raises(ValueError, match="No seed papers were resolved"):
        await ResearchPipeline(sessions, provider, embedding_service).run(project_id, job_id)

    with Session(engine) as session:
        failed = session.get(ResearchJobModel, job_id)
        assert failed.status == ResearchJobStatus.FAILED.value
        assert failed.progress == 1.0
        assert failed.started_at is not None
        assert failed.finished_at is not None
        assert "No seed papers were resolved" in failed.error_message
        assert session.scalar(select(func.count()).select_from(ProjectPaperModel)) == 0
    engine.dispose()


@pytest.mark.asyncio
async def test_pipeline_preserves_failed_state_after_embedding_failure() -> None:
    """
    Проверяет поздний сбой pipeline после discovery и persistence.

    Returns:
        None: Assertions подтверждают FAILED, диагностику и сохранённые counters.

    Fallbacks:
        Ошибка всех embedding attempts не оставляет job в промежуточном EMBEDDING.
    """

    # Persist a valid project that reaches the embedding stage.
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    project_id = uuid4()
    job_id = uuid4()
    with Session(engine) as session:
        session.add(
            ResearchProjectModel(
                id=project_id,
                name="Research",
                config=asdict(ResearchConfig()),
            )
        )
        session.add(
            ResearchQuestionModel(
                id=uuid4(),
                project_id=project_id,
                text="Which paper is relevant?",
            )
        )
        session.add(
            RelatedWorkEntryModel(
                project_id=project_id,
                local_id="RW01",
                title="Seed Paper",
                year=2024,
                source="DOI:10.1000/seed",
            )
        )
        session.add(
            ResearchJobModel(
                id=job_id,
                project_id=project_id,
                status=ResearchJobStatus.PENDING.value,
                progress=0.0,
                papers_discovered=0,
                papers_processed=0,
            )
        )
        session.commit()

    # Resolve and persist the seed, then fail every batch and individual encoding attempt.
    seed = ProviderPaper("seed", "Seed Paper", {"doi": "10.1000/seed"}, year=2024)
    provider = Mock(spec=ScholarlyProvider)
    provider.get_paper = AsyncMock(return_value=seed)
    provider.search_papers = AsyncMock(return_value=[])
    provider.get_papers_batch = AsyncMock(return_value=[seed])
    provider.get_references = AsyncMock(return_value=[])
    provider.get_citations = AsyncMock(return_value=[])
    encoder = Mock()
    encoder.get_sentence_embedding_dimension.return_value = 2
    encoder.encode.side_effect = RuntimeError("embedding backend unavailable")
    embedding_service = EmbeddingService("fixture", "1", 2, 4, encoder)

    with pytest.raises(ValueError, match="No paper embeddings could be created or loaded"):
        await ResearchPipeline(sessions, provider, embedding_service).run(project_id, job_id)

    with Session(engine) as session:
        failed = session.get(ResearchJobModel, job_id)
        assert failed.status == ResearchJobStatus.FAILED.value
        assert failed.progress == 1.0
        assert failed.papers_discovered == 1
        assert failed.papers_processed == 1
        assert failed.error_message == "No paper embeddings could be created or loaded"
        assert session.scalar(select(func.count()).select_from(ProjectPaperModel)) == 1
        assert session.scalar(select(func.count()).select_from(PaperEmbeddingModel)) == 0
    engine.dispose()
