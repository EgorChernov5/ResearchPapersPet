from dataclasses import asdict
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from app.domain.paper import ProviderPaper
from app.domain.project import ResearchConfig
from app.domain.research_job import ResearchJobStatus
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
    engine.dispose()
