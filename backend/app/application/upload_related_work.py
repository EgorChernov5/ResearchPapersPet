from uuid import UUID

from sqlalchemy.orm import sessionmaker

from app.application.exceptions import ResourceNotFoundError
from app.domain.related_work import RelatedWorkEntry
from app.repositories.projects import ProjectRepository
from app.research.related_work_parser import RelatedWorkParser


class UploadRelatedWork:
    """
    Разбирает upload в памяти и заменяет project-scoped Related Work entries.

    Attributes:
        session_factory (sessionmaker): Фабрика SQLAlchemy sessions.
        parser (RelatedWorkParser): XLSX/CSV parser.

    Fallbacks:
        Invalid file не изменяет уже сохранённые entries.
    """

    def __init__(self, session_factory: sessionmaker, parser: RelatedWorkParser) -> None:
        """
        Создаёт upload use case.

        Parameters:
            session_factory (sessionmaker): Фабрика transaction sessions.
            parser (RelatedWorkParser): Проверенный tabular parser.

        Returns:
            None: Метод сохраняет dependencies.

        Fallbacks:
            Parser можно заменить fixture в tests.
        """

        self.session_factory = session_factory
        self.parser = parser

    def execute(
        self,
        project_id: UUID,
        content: bytes,
        filename: str,
    ) -> list[RelatedWorkEntry]:
        """
        Парсит и сохраняет Related Work.

        Parameters:
            project_id (UUID): Идентификатор проекта.
            content (bytes): Uploaded file content.
            filename (str): Имя для выбора parser backend.

        Returns:
            list[RelatedWorkEntry]: Сохранённые entries.

        Fallbacks:
            Missing project даёт ResourceNotFoundError; parse error передаётся API.
        """

        # Parse before opening a write transaction so invalid input changes nothing.
        entries = self.parser.parse_bytes(content, filename)
        with self.session_factory() as session:
            repository = ProjectRepository(session)
            if repository.get_config(project_id) is None:
                raise ResourceNotFoundError(f"Research project {project_id} was not found")
            repository.replace_related_work(project_id, entries)
            session.commit()
            return entries
