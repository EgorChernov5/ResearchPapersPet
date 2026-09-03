from dataclasses import dataclass, field

from app.domain.citation import Citation
from app.domain.scoring import RankedPaper


@dataclass(slots=True)
class ProjectGraph:
    """
    Отфильтрованное представление project citation graph для API.

    Attributes:
        papers (list[RankedPaper]): Graph nodes с metadata и scores.
        citations (list[Citation]): Edges, обе стороны которых входят в nodes.

    Fallbacks:
        Проект без результатов возвращает пустые nodes и edges.
    """

    papers: list[RankedPaper] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
