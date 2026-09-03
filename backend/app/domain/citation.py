from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass(slots=True)
class Citation:
    """
    Глобальное направленное ребро source cites target.

    Attributes:
        source_paper_id (UUID): Цитирующая статья.
        target_paper_id (UUID): Цитируемая статья.
        id (UUID): Внутренний identifier ребра.

    Fallbacks:
        Persistence constraints предотвращают неполные и duplicate edges.
    """

    source_paper_id: UUID
    target_paper_id: UUID
    id: UUID = field(default_factory=uuid4)
