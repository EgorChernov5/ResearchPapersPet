from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4


class ResearchJobStatus(StrEnum):
    """
    Допустимые состояния background research pipeline.

    Attributes:
        PENDING (str): Job создан и ожидает worker.
        COMPLETED (str): Pipeline успешно завершён.
        FAILED (str): Pipeline завершён с ошибкой.

    Fallbacks:
        Неизвестные строки отклоняются enum-конструктором.
    """

    PENDING = "PENDING"
    RESOLVING_SEEDS = "RESOLVING_SEEDS"
    DISCOVERING = "DISCOVERING"
    EMBEDDING = "EMBEDDING"
    SCORING = "SCORING"
    GRAPH_ANALYSIS = "GRAPH_ANALYSIS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(slots=True)
class ResearchJob:
    """
    Состояние фонового research job.

    Attributes:
        project_id (UUID): Идентификатор проекта.
        status (ResearchJobStatus): Текущий pipeline status.
        progress (float): Прогресс от 0 до 1.

    Fallbacks:
        Необработанная worker error сохраняется в error_message со статусом FAILED.
    """

    project_id: UUID
    status: ResearchJobStatus = ResearchJobStatus.PENDING
    progress: float = 0.0
    papers_discovered: int = 0
    papers_processed: int = 0
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
