from dataclasses import asdict
from types import SimpleNamespace
from uuid import UUID

import pytest
from app.api.projects import router as projects_router
from app.config import Settings
from app.domain.project import ResearchConfig
from app.infrastructure.database import Base, Database
from app.infrastructure.models import ResearchProjectModel
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.mark.parametrize("max_depth", [1, 5])
def test_research_config_accepts_supported_depth_boundaries(max_depth: int) -> None:
    """
    Проверяет допустимые границы глубины discovery.

    Parameters:
        max_depth (int): Проверяемая допустимая глубина.

    Returns:
        None: Конфигурация создаётся с переданным значением.

    Fallbacks:
        Ошибка конструктора означает нарушение публичного контракта.
    """

    # Construct the real domain configuration at both supported boundaries.
    assert ResearchConfig(max_depth=max_depth).max_depth == max_depth


@pytest.mark.parametrize("max_depth", [0, 6])
def test_research_config_rejects_unsupported_depth(max_depth: int) -> None:
    """
    Проверяет отклонение глубины вне диапазона 1–5.

    Parameters:
        max_depth (int): Проверяемая недопустимая глубина.

    Returns:
        None: Конструктор поднимает ValueError.

    Fallbacks:
        Отсутствие ошибки означает выход за ограниченный traversal contract.
    """

    # Reject an invalid depth before persistence or job creation.
    with pytest.raises(ValueError, match="max_depth must be between 1 and 5"):
        ResearchConfig(max_depth=max_depth)


def test_old_persisted_config_receives_new_defaults() -> None:
    """
    Проверяет совместимое чтение JSON старого проекта.

    Returns:
        None: Новые поля получают согласованные defaults.

    Fallbacks:
        Старые сохранённые поля остаются без изменений.
    """

    # Reconstruct a configuration from the subset persisted before phase two.
    config = ResearchConfig(max_depth=1, max_papers=40, top_k_expansion=4)

    assert config.max_depth == 1
    assert config.expand_references_topic_threshold == 0.75
    assert config.pdf_top_n == 20
    assert config.allow_manual_pdf_upload is False


def test_project_api_persists_and_returns_phase_two_config() -> None:
    """
    Проверяет HTTP serialization и persistence всех новых настроек этапа.

    Returns:
        None: POST и GET возвращают одинаковую полную конфигурацию.

    Fallbacks:
        SQLite проверяет JSON contract без внешних сервисов.
    """

    # Compose the real API and repository over an isolated relational database.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    application = FastAPI()
    application.state.database = SimpleNamespace(session_factory=sessions)
    application.include_router(projects_router)
    client = TestClient(application)
    config = {
        **asdict(ResearchConfig()),
        "max_depth": 5,
        "max_papers": 125,
        "top_k_expansion": 7,
        "expand_references_topic_threshold": 0.61,
        "pdf_top_n": 13,
        "allow_manual_pdf_upload": True,
    }

    # Read the project back through HTTP so persistence is part of the assertion.
    created = client.post("/projects", json={"name": "Phase 2", "config": config})
    project_id = UUID(created.json()["id"])
    loaded = client.get(f"/projects/{project_id}")

    assert created.status_code == 201
    assert loaded.status_code == 200
    assert loaded.json()["config"] == config
    engine.dispose()


def test_project_api_rejects_questions_above_expansion_capacity() -> None:
    """
    Проверяет невозможную гарантию представительства вопросов.

    Returns:
        None: API отвечает 422 и не сохраняет вопросы.

    Fallbacks:
        Проект остаётся доступен для повторной попытки с меньшим списком.
    """

    # Create a project whose global level limit can represent only one question.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    application = FastAPI()
    application.state.database = SimpleNamespace(session_factory=sessions)
    application.include_router(projects_router)
    client = TestClient(application)
    created = client.post(
        "/projects",
        json={"name": "Capacity", "config": {"top_k_expansion": 1}},
    )
    project_id = created.json()["id"]

    # Reject the whole batch and verify that no partial questions were persisted.
    response = client.post(
        f"/projects/{project_id}/questions",
        json={"questions": ["Question one?", "Question two?"]},
    )
    loaded = client.get(f"/projects/{project_id}")

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "top_k_expansion must be greater than or equal to the research question count"
    )
    assert loaded.json()["questions"] == []
    engine.dispose()


@pytest.mark.service_integration
def test_project_config_round_trip_through_postgresql_api() -> None:
    """
    Проверяет новый config contract через настоящий PostgreSQL и API.

    Returns:
        None: API повторно читает настройки из PostgreSQL.

    Fallbacks:
        Тест требует поднятого postgres и применённых migrations.
    """

    # Use the configured PostgreSQL service without creating an in-memory substitute.
    database = Database(Settings())
    application = FastAPI()
    application.state.database = database
    application.include_router(projects_router)
    client = TestClient(application)
    config = {
        **asdict(ResearchConfig()),
        "max_depth": 1,
        "max_papers": 45,
        "top_k_expansion": 3,
        "expand_references_topic_threshold": 0.55,
        "pdf_top_n": 8,
        "allow_manual_pdf_upload": True,
    }

    # Create and read through the public API so both operations cross PostgreSQL persistence.
    project_id = None
    try:
        created = client.post(
            "/projects",
            json={"name": "PostgreSQL acceptance", "config": config},
        )
        assert created.status_code == 201
        project_id = UUID(created.json()["id"])
        response = client.get(f"/projects/{project_id}")
        assert response.status_code == 200
        assert response.json()["config"] == config
    finally:
        if project_id is not None:
            with database.session_factory() as session:
                session.execute(
                    delete(ResearchProjectModel).where(ResearchProjectModel.id == project_id)
                )
                session.commit()
        database.dispose()
