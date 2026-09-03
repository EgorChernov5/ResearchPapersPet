from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

from app.api.projects import router as projects_router
from app.api.research import router as research_router
from app.api.results import router as results_router
from app.domain.research_job import ResearchJobStatus
from app.infrastructure.database import Base
from app.infrastructure.models import (
    CitationModel,
    PaperModel,
    ProjectPaperModel,
    ProjectPaperQuestionScoreModel,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def test_api_project_setup_job_and_filtered_results() -> None:
    """
    Проверяет Milestone 8 HTTP flow без live provider и worker execution.

    Returns:
        None: Assertions подтверждают setup, enqueue, status, ranking, details и graph.

    Fallbacks:
        In-memory database и mock Redis исключают внешние dependencies.
    """

    # Compose the routers with fixture infrastructure instead of production lifespan.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    redis = Mock()
    application = FastAPI()
    application.state.database = SimpleNamespace(session_factory=sessions)
    application.state.redis = SimpleNamespace(client=redis)
    application.include_router(projects_router)
    application.include_router(research_router)
    application.include_router(results_router)
    client = TestClient(application)

    # Create a project, add one question, and upload a minimal UTF-8 CSV.
    create_response = client.post("/projects", json={"name": "API Research"})
    assert create_response.status_code == 201
    project_id = UUID(create_response.json()["id"])
    question_response = client.post(
        f"/projects/{project_id}/questions",
        json={"questions": ["Which paper is most relevant?"]},
    )
    assert question_response.status_code == 201
    question_id = UUID(question_response.json()["questions"][0]["id"])
    project_response = client.get(f"/projects/{project_id}")
    assert project_response.status_code == 200
    assert len(project_response.json()["questions"]) == 1
    upload_response = client.post(
        f"/projects/{project_id}/related-work",
        files={
            "file": (
                "related.csv",
                "ID,Название\nRW01,Seed Paper\n".encode(),
                "text/csv",
            )
        },
    )
    assert upload_response.status_code == 200
    assert upload_response.json()["entries_count"] == 1

    # Enqueue work without running research inside the HTTP request.
    start_response = client.post(f"/projects/{project_id}/research")
    assert start_response.status_code == 202
    assert start_response.json()["status"] == ResearchJobStatus.PENDING.value
    job_id = UUID(start_response.json()["id"])
    redis.rpush.assert_called_once()
    status_response = client.get(f"/research/{job_id}")
    assert status_response.status_code == 200
    assert status_response.json()["progress"] == 0.0

    # Persist completed ranking fixtures for read-only result endpoints.
    seed_id = uuid4()
    discovered_id = uuid4()
    with Session(engine) as session:
        session.add_all(
            [
                PaperModel(
                    id=seed_id,
                    semantic_scholar_id="seed",
                    title="Seed Paper",
                    abstract="Seed abstract",
                    year=2024,
                    citation_count=100,
                    authors=["Researcher"],
                    categories=["NLP"],
                ),
                PaperModel(
                    id=discovered_id,
                    semantic_scholar_id="discovered",
                    title="Discovered Paper",
                    abstract="Discovered abstract",
                    year=2022,
                    citation_count=20,
                    authors=["Scientist"],
                    categories=["Graph"],
                ),
            ]
        )
        session.add_all(
            [
                ProjectPaperModel(
                    project_id=project_id,
                    paper_id=seed_id,
                    is_seed=True,
                    depth=0,
                    topic_score=0.9,
                    impact_score=0.8,
                    graph_score=0.7,
                    final_score=0.84,
                ),
                ProjectPaperModel(
                    project_id=project_id,
                    paper_id=discovered_id,
                    is_seed=False,
                    depth=1,
                    topic_score=0.6,
                    impact_score=0.5,
                    graph_score=0.4,
                    final_score=0.55,
                ),
            ]
        )
        session.add(CitationModel(source_paper_id=discovered_id, target_paper_id=seed_id))
        session.add(
            ProjectPaperQuestionScoreModel(
                project_id=project_id,
                paper_id=seed_id,
                question_id=question_id,
                query_similarity=0.9,
                topic_score=0.9,
            )
        )
        session.commit()

    # Apply filters to persisted scores without enqueueing another job.
    ranking_response = client.get(
        f"/projects/{project_id}/ranking",
        params={"min_final_score": 0.7},
    )
    assert ranking_response.status_code == 200
    assert ranking_response.json()["count"] == 1
    assert ranking_response.json()["papers"][0]["paper_id"] == str(seed_id)
    papers_response = client.get(
        f"/projects/{project_id}/papers",
        params={"category": "graph"},
    )
    assert papers_response.status_code == 200
    assert papers_response.json()["papers"][0]["paper_id"] == str(discovered_id)

    # Return details and keep only edges whose endpoints survive graph filters.
    details_response = client.get(f"/projects/{project_id}/papers/{seed_id}")
    assert details_response.status_code == 200
    assert len(details_response.json()["question_scores"]) == 1
    graph_response = client.get(
        f"/projects/{project_id}/graph",
        params={"min_final_score": 0.5},
    )
    assert graph_response.status_code == 200
    assert len(graph_response.json()["nodes"]) == 2
    assert len(graph_response.json()["edges"]) == 1
    filtered_graph_response = client.get(
        f"/projects/{project_id}/graph",
        params={"min_final_score": 0.8},
    )
    assert len(filtered_graph_response.json()["nodes"]) == 1
    assert filtered_graph_response.json()["edges"] == []

    # Reject unsupported sorting and unknown resources with explicit HTTP errors.
    assert (
        client.get(
            f"/projects/{project_id}/ranking",
            params={"sort_by": "unsupported"},
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/projects/{project_id}/ranking",
            params={"min_final_score": 2},
        ).status_code
        == 422
    )
    assert client.get(f"/research/{uuid4()}").status_code == 404
    assert redis.rpush.call_count == 1
    engine.dispose()
