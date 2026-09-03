from uuid import UUID

from sqlalchemy.orm import sessionmaker

from app.application.exceptions import ResourceNotFoundError
from app.domain.research_job import ResearchJob
from app.repositories.research_jobs import ResearchJobRepository


class GetResearchStatus:
    """
    Возвращает observable state background ResearchJob.

    Attributes:
        session_factory (sessionmaker): Фабрика SQLAlchemy sessions.

    Fallbacks:
        Missing job преобразуется в ResourceNotFoundError.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        """
        Создаёт read use case.

        Parameters:
            session_factory (sessionmaker): Фабрика transaction sessions.

        Returns:
            None: Метод сохраняет dependency.

        Fallbacks:
            Session закрывается после чтения.
        """

        self.session_factory = session_factory

    def execute(self, job_id: UUID) -> ResearchJob:
        """
        Загружает job status.

        Parameters:
            job_id (UUID): Идентификатор job.

        Returns:
            ResearchJob: Persistent job state.

        Fallbacks:
            Missing job даёт ResourceNotFoundError.
        """

        with self.session_factory() as session:
            job = ResearchJobRepository(session).get(job_id)
            if job is None:
                raise ResourceNotFoundError(f"Research job {job_id} was not found")
            return job
