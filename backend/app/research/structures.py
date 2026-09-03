from dataclasses import dataclass, field

from app.domain.paper import ProviderPaper


@dataclass(slots=True)
class DiscoveredPaper:
    """
    Provider paper с project-specific discovery attributes.

    Attributes:
        paper (ProviderPaper): Нормализованные глобальные metadata.
        is_seed (bool): Признак исходной seed paper.
        depth (int): Минимальная глубина от seed.

    Fallbacks:
        На текущем этапе depth принимает только 0 или 1.
    """

    paper: ProviderPaper
    is_seed: bool
    depth: int


@dataclass(frozen=True, slots=True)
class DiscoveredCitation:
    """
    Citation edge в provider identifiers до persistence.

    Attributes:
        source_paper_id (str): Provider ID цитирующей статьи.
        target_paper_id (str): Provider ID цитируемой статьи.

    Fallbacks:
        Self edges и incomplete edges не создаются discovery layer.
    """

    source_paper_id: str
    target_paper_id: str


@dataclass(slots=True)
class DiscoveryFailure:
    """
    Изолированная ошибка одного citation discovery request.

    Attributes:
        paper_id (str): Provider ID seed paper.
        direction (str): Направление references или citations.
        reason (str): Понятная причина provider failure.

    Fallbacks:
        Ошибка сохраняется в result и не останавливает другие seeds.
    """

    paper_id: str
    direction: str
    reason: str


@dataclass(slots=True)
class CitationDiscoveryResult:
    """
    Результат bounded citation discovery depth=1.

    Attributes:
        papers (list[DiscoveredPaper]): Seeds и выбранные neighbors.
        citations (list[DiscoveredCitation]): Уникальные направленные edges.
        failures (list[DiscoveryFailure]): Изолированные provider failures.

    Fallbacks:
        Пустое neighborhood возвращает только seed papers.
    """

    papers: list[DiscoveredPaper] = field(default_factory=list)
    citations: list[DiscoveredCitation] = field(default_factory=list)
    failures: list[DiscoveryFailure] = field(default_factory=list)
