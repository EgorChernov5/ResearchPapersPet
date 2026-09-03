from dataclasses import dataclass, field


@dataclass(slots=True)
class ResolvedSeedPaper:
    """
    Успешно разрешённая canonical seed paper.

    Attributes:
        local_id (str): ID исходной Related Work строки.
        paper_id (str): Canonical provider paper ID.
        semantic_scholar_id (str): Semantic Scholar paper ID.

    Fallbacks:
        Missing year остаётся None, а identifiers могут содержать только Semantic Scholar.
    """

    local_id: str
    paper_id: str
    semantic_scholar_id: str
    title: str
    year: int | None
    external_ids: dict[str, str]
    resolution_method: str
    resolution_confidence: float
    original_source: str | None


@dataclass(slots=True)
class SeedResolutionFailure:
    """
    Диагностируемая ошибка разрешения одной seed paper.

    Attributes:
        local_id (str): ID исходной Related Work строки.
        reason (str): Понятное описание причины.
        original_source (str | None): Исходный identifier или URL.

    Fallbacks:
        Failure добавляется в результат и не останавливает остальные seeds.
    """

    local_id: str
    reason: str
    original_source: str | None


@dataclass(slots=True)
class SeedResolutionResult:
    """
    Полный результат batch seed resolution.

    Attributes:
        resolved (list[ResolvedSeedPaper]): Успешно разрешённые seeds.
        failures (list[SeedResolutionFailure]): Изолированные ошибки seeds.

    Fallbacks:
        Полностью неуспешный batch возвращает пустой resolved без exception.
    """

    resolved: list[ResolvedSeedPaper] = field(default_factory=list)
    failures: list[SeedResolutionFailure] = field(default_factory=list)
