import json
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import sessionmaker

from app.application.exceptions import ResourceNotFoundError
from app.domain.research_job import ResearchJob, ResearchJobStatus
from app.repositories.projects import ProjectRepository
from app.repositories.research_jobs import ResearchJobRepository


class StartResearch:
    """
    Создаёт persistent ResearchJob и ставит его в Redis queue.

    Attributes:
        session_factory (sessionmaker): Фабрика SQLAlchemy sessions.
        redis (Redis): Redis queue client.
        queue_name (str): Имя research queue.

    Fallbacks:
        Queue failure переводит уже созданную job в FAILED.
    """

    def __init__(
        self,
        session_factory: sessionmaker,
        redis: Redis,
        queue_name: str,
    ) -> None:
        """
        Создаёт use case с explicit dependencies.

        Parameters:
            session_factory (sessionmaker): Фабрика SQLAlchemy sessions.
            redis (Redis): Redis queue client.
            queue_name (str): Имя queue.

        Returns:
            None: Метод инициализирует use case.

        Fallbacks:
            Dependencies могут заменяться recorded fixtures в tests.
        """

        self.session_factory = session_factory
        self.redis = redis
        self.queue_name = queue_name

    def execute(self, project_id: UUID) -> ResearchJob:
        """
        Валидирует проект, создаёт job и публикует queue envelope.

        Parameters:
            project_id (UUID): Идентификатор ResearchProject.

        Returns:
            ResearchJob: Job в статусе PENDING.

        Fallbacks:
            Missing project даёт ValueError; RedisError сохраняет FAILED job.
        """

        with self.session_factory() as session:
            projects = ProjectRepository(session)
            if projects.get_config(project_id) is None:
                raise ResourceNotFoundError(f"Research project {project_id} was not found")
            if not projects.get_seed_identities(project_id):
                raise ValueError("Research project has no Related Work entries")
            if not projects.get_questions(project_id):
                raise ValueError("Research project has no research questions")
            jobs = ResearchJobRepository(session)
            job = jobs.create(project_id)
            session.commit()
            try:
                self.redis.rpush(
                    self.queue_name,
                    json.dumps(
                        {
                            "project_id": str(project_id),
                            "job_id": str(job.id),
                        }
                    ),
                )
            except RedisError as error:
                jobs.update(
                    job.id,
                    ResearchJobStatus.FAILED,
                    1.0,
                    error_message=f"Cannot enqueue research job: {error}",
                )
                session.commit()
                raise
            return job
