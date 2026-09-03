from uuid import UUID

from sqlalchemy.orm import sessionmaker

from app.application.exceptions import ResourceNotFoundError
from app.domain.project import ResearchConfig, ResearchProject, ResearchQuestion
from app.repositories.projects import ProjectRepository


class CreateProject:
    """
    Создаёт research project через transaction boundary.

    Attributes:
        session_factory (sessionmaker): Фабрика SQLAlchemy sessions.

    Fallbacks:
        Domain validation отклоняет invalid name или configuration.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        """
        Создаёт use case.

        Parameters:
            session_factory (sessionmaker): Фабрика transaction sessions.

        Returns:
            None: Метод сохраняет dependency.

        Fallbacks:
            Database errors передаются API exception handler.
        """

        self.session_factory = session_factory

    def execute(self, name: str, config: ResearchConfig) -> ResearchProject:
        """
        Создаёт и сохраняет проект.

        Parameters:
            name (str): Пользовательское имя проекта.
            config (ResearchConfig): Project configuration.

        Returns:
            ResearchProject: Persistent domain project.

        Fallbacks:
            Transaction rollback выполняется context manager при exception.
        """

        with self.session_factory() as session:
            project = ProjectRepository(session).create(name, config)
            session.commit()
            return project


class GetProject:
    """
    Возвращает project setup вместе с research questions.

    Attributes:
        session_factory (sessionmaker): Фабрика SQLAlchemy sessions.

    Fallbacks:
        Missing project преобразуется в ResourceNotFoundError.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        """
        Создаёт use case.

        Parameters:
            session_factory (sessionmaker): Фабрика transaction sessions.

        Returns:
            None: Метод сохраняет dependency.

        Fallbacks:
            Session закрывается после чтения.
        """

        self.session_factory = session_factory

    def execute(self, project_id: UUID) -> ResearchProject:
        """
        Загружает проект.

        Parameters:
            project_id (UUID): Идентификатор проекта.

        Returns:
            ResearchProject: Найденный domain project.

        Fallbacks:
            Missing project даёт ResourceNotFoundError.
        """

        with self.session_factory() as session:
            project = ProjectRepository(session).get(project_id)
            if project is None:
                raise ResourceNotFoundError(f"Research project {project_id} was not found")
            return project


class AddResearchQuestions:
    """
    Добавляет список research questions к существующему проекту.

    Attributes:
        session_factory (sessionmaker): Фабрика SQLAlchemy sessions.

    Fallbacks:
        Missing project даёт ResourceNotFoundError; empty input отклоняется.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        """
        Создаёт use case.

        Parameters:
            session_factory (sessionmaker): Фабрика transaction sessions.

        Returns:
            None: Метод сохраняет dependency.

        Fallbacks:
            Database transaction контролируется execute.
        """

        self.session_factory = session_factory

    def execute(self, project_id: UUID, texts: list[str]) -> list[ResearchQuestion]:
        """
        Проверяет и сохраняет вопросы.

        Parameters:
            project_id (UUID): Идентификатор проекта.
            texts (list[str]): Тексты новых вопросов.

        Returns:
            list[ResearchQuestion]: Созданные questions.

        Fallbacks:
            Пустой список отклоняется ValueError.
        """

        if not texts:
            raise ValueError("At least one research question is required")
        with self.session_factory() as session:
            repository = ProjectRepository(session)
            if repository.get_config(project_id) is None:
                raise ResourceNotFoundError(f"Research project {project_id} was not found")
            questions = repository.add_questions(project_id, texts)
            session.commit()
            return questions
