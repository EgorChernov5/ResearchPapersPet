from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.research_job import ResearchJob, ResearchJobStatus
from app.infrastructure.models import ResearchJobModel


class ResearchJobRepository:
    """
    Управляет persistent lifecycle background research jobs.

    Attributes:
        session (Session): Текущая SQLAlchemy transaction session.

    Fallbacks:
        Missing job возвращает None; invalid status отклоняется domain enum.
    """

    def __init__(self, session: Session) -> None:
        """
        Создаёт research job repository.

        Parameters:
            session (Session): SQLAlchemy session.

        Returns:
            None: Метод сохраняет session.

        Fallbacks:
            Commit и rollback выполняет application layer.
        """

        self.session = session

    def create(self, project_id: UUID) -> ResearchJob:
        """
        Создаёт job в статусе PENDING.

        Parameters:
            project_id (UUID): Идентификатор проекта.

        Returns:
            ResearchJob: Созданная доменная job.

        Fallbacks:
            Foreign key отклоняет неизвестный project при flush/commit.
        """

        model = ResearchJobModel(
            project_id=project_id,
            status=ResearchJobStatus.PENDING.value,
            progress=0.0,
            papers_discovered=0,
            papers_processed=0,
        )
        self.session.add(model)
        self.session.flush()
        return self._to_domain(model)

    def get(self, job_id: UUID) -> ResearchJob | None:
        """
        Загружает job по identifier.

        Parameters:
            job_id (UUID): Идентификатор research job.

        Returns:
            ResearchJob | None: Доменная job или None.

        Fallbacks:
            Missing row не создаёт exception.
        """

        model = self.session.get(ResearchJobModel, job_id)
        return self._to_domain(model) if model is not None else None

    def update(
        self,
        job_id: UUID,
        status: ResearchJobStatus,
        progress: float,
        papers_discovered: int | None = None,
        papers_processed: int | None = None,
        error_message: str | None = None,
    ) -> ResearchJob:
        """
        Обновляет observable job state и timestamps.

        Parameters:
            job_id (UUID): Идентификатор research job.
            status (ResearchJobStatus): Новый pipeline status.
            progress (float): Прогресс от 0 до 1.
            papers_discovered (int | None): Найденные papers. По умолчанию: None.
            papers_processed (int | None): Сохранённые papers. По умолчанию: None.
            error_message (str | None): Failure diagnostics. По умолчанию: None.

        Returns:
            ResearchJob: Обновлённая доменная job.

        Fallbacks:
            Missing job вызывает ValueError с job ID.
        """

        model = self.session.get(ResearchJobModel, job_id)
        if model is None:
            raise ValueError(f"Research job {job_id} was not found")
        model.status = status.value
        # Never move observable progress backwards when stages are retried or nested.
        model.progress = max(model.progress, min(max(progress, 0.0), 1.0))
        if model.started_at is None and status != ResearchJobStatus.PENDING:
            model.started_at = datetime.now(UTC)
        if papers_discovered is not None:
            model.papers_discovered = papers_discovered
        if papers_processed is not None:
            model.papers_processed = papers_processed
        model.error_message = error_message
        if status in (ResearchJobStatus.COMPLETED, ResearchJobStatus.FAILED):
            model.finished_at = datetime.now(UTC)
        self.session.flush()
        return self._to_domain(model)

    def _to_domain(self, model: ResearchJobModel) -> ResearchJob:
        """
        Преобразует persistence model в domain entity.

        Parameters:
            model (ResearchJobModel): SQLAlchemy research job row.

        Returns:
            ResearchJob: Framework-independent domain entity.

        Fallbacks:
            Invalid stored status вызывает ResearchJobStatus ValueError.
        """

        return ResearchJob(
            id=model.id,
            project_id=model.project_id,
            status=ResearchJobStatus(model.status),
            progress=model.progress,
            papers_discovered=model.papers_discovered,
            papers_processed=model.papers_processed,
            error_message=model.error_message,
            started_at=model.started_at,
            finished_at=model.finished_at,
        )
