import json
from dataclasses import asdict
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from app.api.results import router as results_router
from app.application.start_research import StartResearch
from app.config import Settings
from app.domain.paper import ProviderPaper
from app.domain.project import ResearchConfig
from app.domain.research_job import ResearchJobStatus
from app.infrastructure.database import Database
from app.infrastructure.models import (
    CitationModel,
    PaperEmbeddingModel,
    PaperModel,
    RelatedWorkEntryModel,
    ResearchProjectModel,
    ResearchQuestionModel,
)
from app.infrastructure.redis import RedisConnection
from app.providers.base import ScholarlyProvider
from app.research.embeddings import EmbeddingService
from app.research.pipeline import ResearchPipeline
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, or_, select


@pytest.mark.asyncio
@pytest.mark.service_integration
async def test_pipeline_uses_postgresql_pgvector_and_redis_for_depth_two() -> None:
    """
    Проверяет полный depth-two pipeline с настоящими PostgreSQL/pgvector и Redis queue.

    Returns:
        None: Повторный job не дублирует graph, embeddings или ranking state.

    Fallbacks:
        Provider и encoder детерминированы; service boundaries остаются реальными контейнерами.
    """

    # Create isolated service-backed input and a unique Redis queue.
    settings = Settings()
    database = Database(settings)
    redis_connection = RedisConnection(settings)
    queue_name = f"research-pipeline-integration-{uuid4()}"
    project_id = uuid4()
    question_id = uuid4()
    test_suffix = uuid4().hex
    seed_provider_id = f"pipeline-seed-{test_suffix}"
    level_one_provider_id = f"pipeline-depth-one-{test_suffix}"
    level_two_provider_id = f"pipeline-depth-two-{test_suffix}"
    provider_ids = {seed_provider_id, level_one_provider_id, level_two_provider_id}
    config = ResearchConfig(
        max_depth=2,
        max_papers=3,
        top_k_expansion=1,
        expand_references_topic_threshold=0.0,
    )
    with database.session_factory() as session:
        # Flush the parent explicitly because persistence models expose no ORM relationships.
        session.add(
            ResearchProjectModel(
                id=project_id,
                name="Pipeline service integration",
                config=asdict(config),
            )
        )
        session.flush()

        # Add dependent inputs only after PostgreSQL can resolve their project foreign key.
        session.add(
            ResearchQuestionModel(
                id=question_id,
                project_id=project_id,
                text="Which graph descendants are semantically relevant?",
            )
        )
        session.add(
            RelatedWorkEntryModel(
                project_id=project_id,
                local_id="RW01",
                title="Pipeline Seed",
                year=2024,
                source=f"DOI:10.1000/pipeline-seed-{test_suffix}",
            )
        )
        session.commit()

    seed = ProviderPaper(
        seed_provider_id,
        "Pipeline Seed",
        {"doi": f"10.1000/pipeline-seed-{test_suffix}"},
        year=2024,
    )
    level_one = ProviderPaper(level_one_provider_id, "Pipeline Depth One", {}, year=2023)
    level_two = ProviderPaper(level_two_provider_id, "Pipeline Depth Two", {}, year=2022)
    provider = Mock(spec=ScholarlyProvider)
    provider.get_paper = AsyncMock(return_value=seed)
    provider.search_papers = AsyncMock(return_value=[])
    provider.get_papers_batch = AsyncMock(return_value=[seed])
    provider.get_references = AsyncMock(
        side_effect=lambda paper_id, **kwargs: {
            seed_provider_id: [level_one],
            level_one_provider_id: [level_two],
        }.get(paper_id, [])
    )
    provider.get_citations = AsyncMock(return_value=[])
    encoder = Mock()
    encoder.get_embedding_dimension.return_value = 768
    encoder.encode.side_effect = lambda texts, **kwargs: [[1.0] + [0.0] * 767 for _ in texts]
    embedding_service = EmbeddingService("pipeline-fixture", "phase-2-stage-5", 768, 4, encoder)

    try:
        # Enqueue and consume two jobs through the real Redis list contract.
        for _ in range(2):
            job = StartResearch(
                database.session_factory,
                redis_connection.client,
                queue_name,
            ).execute(project_id)
            payload = json.loads(redis_connection.client.lpop(queue_name))
            assert UUID(payload["project_id"]) == project_id
            assert UUID(payload["job_id"]) == job.id
            completed = await ResearchPipeline(
                database.session_factory,
                provider,
                embedding_service,
            ).run(project_id, job.id)
            assert completed.status == ResearchJobStatus.COMPLETED

        # Read the persisted public API and verify graph/ranking agreement.
        application = FastAPI()
        application.state.database = database
        application.include_router(results_router)
        client = TestClient(application)
        graph_response = client.get(f"/projects/{project_id}/graph")
        ranking_response = client.get(f"/projects/{project_id}/ranking")
        assert graph_response.status_code == ranking_response.status_code == 200
        graph = graph_response.json()
        ranking = ranking_response.json()
        assert sorted(paper["depth"] for paper in graph["nodes"]) == [0, 1, 2]
        assert len(graph["edges"]) == 2
        assert ranking["count"] == 3
        assert {paper["paper_id"] for paper in graph["nodes"]} == {
            paper["paper_id"] for paper in ranking["papers"]
        }
        with database.session_factory() as session:
            paper_ids = set(
                session.scalars(
                    select(PaperModel.id).where(PaperModel.semantic_scholar_id.in_(provider_ids))
                ).all()
            )
            assert len(paper_ids) == 3
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(PaperEmbeddingModel)
                    .where(
                        PaperEmbeddingModel.paper_id.in_(paper_ids),
                        PaperEmbeddingModel.model_name == embedding_service.model_name,
                        PaperEmbeddingModel.model_version == embedding_service.model_version,
                    )
                )
                == 3
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(CitationModel)
                    .where(
                        CitationModel.source_paper_id.in_(paper_ids),
                        CitationModel.target_paper_id.in_(paper_ids),
                    )
                )
                == 2
            )
    finally:
        # Delete only service data owned by this test and always clear its unique queue.
        redis_connection.client.delete(queue_name)
        with database.session_factory() as session:
            paper_ids = set(
                session.scalars(
                    select(PaperModel.id).where(PaperModel.semantic_scholar_id.in_(provider_ids))
                ).all()
            )
            session.execute(
                delete(ResearchProjectModel).where(ResearchProjectModel.id == project_id)
            )
            if paper_ids:
                session.execute(
                    delete(CitationModel).where(
                        or_(
                            CitationModel.source_paper_id.in_(paper_ids),
                            CitationModel.target_paper_id.in_(paper_ids),
                        )
                    )
                )
                session.execute(
                    delete(PaperEmbeddingModel).where(PaperEmbeddingModel.paper_id.in_(paper_ids))
                )
                session.execute(delete(PaperModel).where(PaperModel.id.in_(paper_ids)))
            session.commit()
        redis_connection.close()
        database.dispose()
