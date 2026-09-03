from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass(slots=True)
class ProjectPaper:
    """
    Project-specific discovery и scoring состояние глобальной статьи.

    Attributes:
        project_id (UUID): Идентификатор проекта.
        paper_id (UUID): Идентификатор глобальной статьи.
        is_seed (bool): Признак seed paper.

    Fallbacks:
        Ещё не рассчитанные scores представлены None, а не нулём.
    """

    project_id: UUID
    paper_id: UUID
    is_seed: bool
    depth: int | None = None
    query_similarity: float | None = None
    seed_similarity: float | None = None
    topic_score: float | None = None
    citation_score: float | None = None
    recency_score: float | None = None
    impact_score: float | None = None
    distance_score: float | None = None
    connectivity_score: float | None = None
    pagerank_score: float | None = None
    graph_score: float | None = None
    final_score: float | None = None
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class ProjectPaperQuestionScore:
    """
    Relevance одной статьи относительно одного research question.

    Attributes:
        project_id (UUID): Идентификатор проекта.
        paper_id (UUID): Идентификатор статьи.
        question_id (UUID): Идентификатор вопроса.

    Fallbacks:
        Scores остаются None до semantic-ranking этапа.
    """

    project_id: UUID
    paper_id: UUID
    question_id: UUID
    query_similarity: float | None = None
    topic_score: float | None = None


@dataclass(slots=True)
class PaperGraphMetrics:
    """
    Graph metrics одной статьи внутри project subgraph.

    Attributes:
        paper_id (UUID): Идентификатор глобальной статьи.
        in_degree (int): Число входящих project citation edges.
        out_degree (int): Число исходящих project citation edges.
        degree_centrality (float): Доля уникальных соседей.
        distance_from_seed (int | None): Кратчайшее undirected расстояние до seed.
        distance_score (float | None): Обратная proximity-оценка.
        connectivity_score (float): Нормализованная локальная связность.
        pagerank_score (float): Нормализованный PageRank.

    Fallbacks:
        Для disconnected paper distance и distance_score остаются None.
    """

    paper_id: UUID
    in_degree: int
    out_degree: int
    degree_centrality: float
    distance_from_seed: int | None
    distance_score: float | None
    connectivity_score: float
    pagerank_score: float


@dataclass(slots=True)
class PaperImpactScore:
    """
    Metadata и graph-based impact одной project paper.

    Attributes:
        paper_id (UUID): Идентификатор глобальной статьи.
        citation_score (float | None): Нормализованный log citation count.
        recency_score (float | None): Exponential age decay.
        pagerank_score (float | None): Нормализованный project PageRank.
        impact_score (float | None): Взвешенная impact-оценка.

    Fallbacks:
        Missing year или citations не интерпретируются как нулевые значения.
    """

    paper_id: UUID
    citation_score: float | None
    recency_score: float | None
    pagerank_score: float | None
    impact_score: float | None


@dataclass(slots=True)
class PaperFinalScore:
    """
    Полный результат graph, impact и final ranking статьи.

    Attributes:
        paper_id (UUID): Идентификатор глобальной статьи.
        citation_score (float | None): Нормализованный citation signal.
        recency_score (float | None): Age-decay signal.
        impact_score (float | None): Aggregated impact signal.
        distance_score (float | None): Proximity к seed papers.
        connectivity_score (float | None): Local graph connectivity.
        pagerank_score (float | None): Нормализованный PageRank.
        graph_score (float | None): Graph proximity/connectivity score.
        final_score (float | None): Итоговая relevance-оценка проекта.

    Fallbacks:
        Веса отсутствующих компонентов перераспределяются между доступными.
    """

    paper_id: UUID
    citation_score: float | None
    recency_score: float | None
    impact_score: float | None
    distance_score: float | None
    connectivity_score: float | None
    pagerank_score: float | None
    graph_score: float | None
    final_score: float | None


@dataclass(slots=True)
class RankedPaper:
    """
    Объединяет global metadata и project-specific ranking state для чтения.

    Attributes:
        paper_id (UUID): Идентификатор глобальной статьи.
        title (str): Каноническое название статьи.
        is_seed (bool): Признак исходной seed paper.
        final_score (float | None): Итоговая project relevance.

    Fallbacks:
        Metadata и scores, отсутствующие у provider или pipeline, остаются None.
    """

    paper_id: UUID
    semantic_scholar_id: str | None
    title: str
    abstract: str | None
    year: int | None
    citation_count: int | None
    influential_citation_count: int | None
    reference_count: int | None
    authors: list[str]
    categories: list[str]
    pdf_url: str | None
    is_seed: bool
    depth: int | None
    query_similarity: float | None
    seed_similarity: float | None
    topic_score: float | None
    citation_score: float | None
    recency_score: float | None
    impact_score: float | None
    distance_score: float | None
    connectivity_score: float | None
    pagerank_score: float | None
    graph_score: float | None
    final_score: float | None


@dataclass(slots=True)
class PaperDetails:
    """
    Полная paper view с отдельными scores по research questions.

    Attributes:
        paper (RankedPaper): Metadata и project-level ranking.
        question_scores (list[ProjectPaperQuestionScore]): Pair-level semantic scores.

    Fallbacks:
        Paper без рассчитанных question scores возвращает пустой список.
    """

    paper: RankedPaper
    question_scores: list[ProjectPaperQuestionScore] = field(default_factory=list)
