from dataclasses import dataclass, field
from uuid import UUID

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
    Результат bounded многоуровневого citation discovery.

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


@dataclass(slots=True)
class DiscoverySelection:
    """
    Результат semantic selection кандидатов одного уровня.

    Attributes:
        papers (list[ProviderPaper]): Выбранные papers в порядке balanced selection.
        preliminary_scores (dict[str, float | None]): Лучший score по provider paper ID.

    Fallbacks:
        Кандидат без доступного score не раскрывает references на следующем уровне.
    """

    papers: list[ProviderPaper] = field(default_factory=list)
    preliminary_scores: dict[str, float | None] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PreliminaryCandidateScore:
    """
    Семантическая оценка кандидата относительно одного research question.

    Attributes:
        paper_id (UUID): Идентификатор глобальной статьи-кандидата.
        question_id (UUID): Идентификатор research question.
        query_similarity (float | None): Cosine similarity кандидата и вопроса.
        seed_similarity (float | None): Максимальная similarity кандидата с seeds.
        preliminary_topic_score (float | None): Взвешенная preliminary relevance.

    Fallbacks:
        Missing vectors дают None и не превращаются в citation или graph signals.
    """

    paper_id: UUID
    question_id: UUID
    query_similarity: float | None
    seed_similarity: float | None
    preliminary_topic_score: float | None


@dataclass(slots=True)
class PreliminaryQuestionShortlist:
    """
    Независимый ranked shortlist одного research question.

    Attributes:
        question_id (UUID): Идентификатор research question.
        candidates (list[PreliminaryCandidateScore]): Кандидаты в порядке убывания score.

    Fallbacks:
        Вопрос без доступных candidate embeddings получает пустой shortlist.
    """

    question_id: UUID
    candidates: list[PreliminaryCandidateScore] = field(default_factory=list)


@dataclass(slots=True)
class PreliminaryScoringResult:
    """
    Результат preliminary scoring до формирования persisted graph.

    Attributes:
        shortlists (list[PreliminaryQuestionShortlist]): Ranked список для каждого вопроса.

    Fallbacks:
        Пустой набор вопросов возвращает пустой результат.
    """

    shortlists: list[PreliminaryQuestionShortlist] = field(default_factory=list)
