from dataclasses import asdict
from uuid import uuid4

from app.domain.paper import ProviderPaper
from app.domain.project import ResearchConfig
from app.domain.research_job import ResearchJobStatus
from app.infrastructure.database import Base
from app.infrastructure.models import (
    CitationModel,
    PaperModel,
    ProjectPaperModel,
    ResearchJobModel,
    ResearchProjectModel,
)
from app.repositories.citations import CitationRepository
from app.repositories.papers import PaperRepository, ProjectPaperRepository
from app.repositories.research_jobs import ResearchJobRepository
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session


def test_repositories_persist_global_and_project_specific_data() -> None:
    """
    Проверяет idempotent Paper/Citation/ProjectPaper persistence.

    Returns:
        None: Assertions подтверждают uniqueness и metadata enrichment.

    Fallbacks:
        In-memory fixture не зависит от PostgreSQL service.
    """

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    project_id = uuid4()
    with Session(engine) as session:
        session.add(ResearchProjectModel(id=project_id, name="Project", config={}))
        session.commit()

        papers = PaperRepository(session)
        first = papers.upsert(
            ProviderPaper(
                paper_id="s2-one",
                title="Paper One",
                external_ids={"doi": "10.1000/one"},
            )
        )
        enriched = papers.upsert(
            ProviderPaper(
                paper_id="s2-one",
                title="Paper One",
                abstract="Abstract",
                year=2024,
                external_ids={"doi": "10.1000/one"},
            )
        )
        second = papers.upsert(
            ProviderPaper(
                paper_id="s2-two",
                title="Paper Two",
                external_ids={},
            )
        )
        project_papers = ProjectPaperRepository(session)
        project_papers.upsert(project_id, first.id, False, 1)
        project_papers.upsert(project_id, first.id, True, 0)
        citations = CitationRepository(session)
        citations.upsert(first.id, second.id)
        citations.upsert(first.id, second.id)
        assert citations.upsert(first.id, first.id) is None
        session.commit()

        assert first.id == enriched.id
        assert session.scalar(select(func.count()).select_from(PaperModel)) == 2
        assert session.scalar(select(PaperModel).where(PaperModel.id == first.id)).abstract == (
            "Abstract"
        )
        association = session.scalar(select(ProjectPaperModel))
        assert association.is_seed is True
        assert association.depth == 0
        assert session.scalar(select(func.count()).select_from(CitationModel)) == 1
    engine.dispose()


def test_research_job_repository_tracks_lifecycle() -> None:
    """
    Проверяет persistent progress, counters и terminal timestamps.

    Returns:
        None: Assertions подтверждают PENDING → DISCOVERING → COMPLETED.

    Fallbacks:
        Invalid missing job отдельно проверяется repository contract.
    """

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    project_id = uuid4()
    with Session(engine) as session:
        session.add(ResearchProjectModel(id=project_id, name="Project", config={}))
        jobs = ResearchJobRepository(session)
        job = jobs.create(project_id)
        jobs.update(job.id, ResearchJobStatus.DISCOVERING, 0.5, papers_discovered=3)
        completed = jobs.update(
            job.id,
            ResearchJobStatus.COMPLETED,
            1.0,
            papers_discovered=3,
            papers_processed=3,
        )
        session.commit()

        assert completed.status == ResearchJobStatus.COMPLETED
        assert completed.started_at is not None
        assert completed.finished_at is not None
        assert completed.papers_discovered == 3
        assert completed.papers_processed == 3
        assert session.scalar(select(func.count()).select_from(ResearchJobModel)) == 1
    engine.dispose()


def test_research_job_repository_never_decreases_progress() -> None:
    """
    Проверяет монотонность observable progress между повторными stage updates.

    Returns:
        None: Более низкое новое значение не уменьшает сохранённый progress.

    Fallbacks:
        Значения по-прежнему ограничиваются диапазоном от нуля до единицы.
    """

    # Create the minimal persisted project and job required by the repository contract.
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    project_id = uuid4()
    with Session(engine) as session:
        session.add(
            ResearchProjectModel(
                id=project_id,
                name="Monotonic progress",
                config=asdict(ResearchConfig()),
            )
        )
        session.commit()
        jobs = ResearchJobRepository(session)
        job = jobs.create(project_id)
        jobs.update(job.id, ResearchJobStatus.DISCOVERING, 0.7)
        repeated = jobs.update(job.id, ResearchJobStatus.DISCOVERING, 0.3)

        assert repeated.progress == 0.7
    engine.dispose()
