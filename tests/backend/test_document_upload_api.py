from pathlib import Path
from types import SimpleNamespace

from app.api.projects import router as projects_router
from app.domain.document import DocumentJobStatus
from app.domain.paper import ProviderPaper
from app.domain.project import ResearchConfig
from app.infrastructure.database import Base
from app.infrastructure.document_storage import LocalVolumeDocumentStorage
from app.repositories.documents import DocumentJobRepository
from app.repositories.papers import PaperRepository, ProjectPaperRepository
from app.repositories.projects import ProjectRepository
from app.repositories.research_jobs import ResearchJobRepository
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def test_manual_pdf_upload_persists_multipart_and_updates_status(tmp_path: Path) -> None:
    """
    Проверяет настоящий multipart upload для разрешённого project/paper target.

    Parameters:
        tmp_path (Path): Временный local document storage.

    Returns:
        None: API сохраняет PDF и возвращает PARSING.

    Fallbacks:
        In-memory DB изолирует HTTP contract от external services.
    """

    # Compose API infrastructure and an AWAITING_UPLOAD target.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    storage = LocalVolumeDocumentStorage(tmp_path, 1_000)
    with sessions() as session:
        project = ProjectRepository(session).create(
            "Manual upload",
            ResearchConfig(allow_manual_pdf_upload=True),
        )
        paper = PaperRepository(session).upsert(ProviderPaper("manual-paper", "Manual Paper", {}))
        ProjectPaperRepository(session).upsert(project.id, paper.id, True, 0)
        research_job = ResearchJobRepository(session).create(project.id)
        target = DocumentJobRepository(session).create_target(
            project.id,
            paper.id,
            research_job.id,
        )
        DocumentJobRepository(session).update_status(
            target.id,
            DocumentJobStatus.AWAITING_UPLOAD,
        )
        session.commit()

    application = FastAPI()
    application.state.database = SimpleNamespace(session_factory=sessions)
    application.state.document_storage = storage
    application.include_router(projects_router)
    client = TestClient(application)

    # Upload through multipart and then read the persisted lifecycle through public API.
    response = client.post(
        f"/projects/{project.id}/papers/{paper.id}/document",
        files={"file": ("paper.pdf", b"%PDF-1.4\nmanual\n%%EOF", "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["status"] == DocumentJobStatus.PARSING.value
    assert response.json()["document_id"] is not None
    listed = client.get(f"/projects/{project.id}/documents")
    assert listed.status_code == 200
    assert listed.json()["documents"][0]["status"] == DocumentJobStatus.PARSING.value
    assert len(list(tmp_path.rglob("*.pdf"))) == 1
    engine.dispose()


def test_manual_pdf_upload_is_rejected_when_project_flag_is_disabled(tmp_path: Path) -> None:
    """
    Проверяет server-side запрет upload при выключенном checkbox.

    Parameters:
        tmp_path (Path): Временный local document storage.

    Returns:
        None: Endpoint возвращает validation error и ничего не сохраняет.

    Fallbacks:
        Искусственный AWAITING status доказывает независимую config authorization.
    """

    # Persist a target whose state alone would otherwise permit manual upload.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    storage = LocalVolumeDocumentStorage(tmp_path, 1_000)
    with sessions() as session:
        project = ProjectRepository(session).create("Disabled upload", ResearchConfig())
        paper = PaperRepository(session).upsert(
            ProviderPaper("disabled-paper", "Disabled Paper", {})
        )
        ProjectPaperRepository(session).upsert(project.id, paper.id, True, 0)
        research_job = ResearchJobRepository(session).create(project.id)
        target = DocumentJobRepository(session).create_target(
            project.id,
            paper.id,
            research_job.id,
        )
        DocumentJobRepository(session).update_status(
            target.id,
            DocumentJobStatus.AWAITING_UPLOAD,
        )
        session.commit()

    application = FastAPI()
    application.state.database = SimpleNamespace(session_factory=sessions)
    application.state.document_storage = storage
    application.include_router(projects_router)
    response = TestClient(application).post(
        f"/projects/{project.id}/papers/{paper.id}/document",
        files={"file": ("paper.pdf", b"%PDF-1.4\nmanual\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 422
    assert "disabled" in response.json()["detail"]
    assert list(tmp_path.rglob("*.pdf")) == []
    engine.dispose()
