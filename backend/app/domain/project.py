from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass(slots=True)
class ResearchConfig:
    """
    Конфигурация controlled research pipeline.

    Attributes:
        max_depth (int): Максимальная глубина citation expansion. По умолчанию: 2.
        max_papers (int): Максимальное число статей. По умолчанию: 300.
        top_k_expansion (int): Число кандидатов на один expansion step. По умолчанию: 20.
        topic_weight (float): Вес topic score в final score. По умолчанию: 0.60.
        impact_weight (float): Вес impact score в final score. По умолчанию: 0.25.
        graph_weight (float): Вес graph score в final score. По умолчанию: 0.15.
        query_similarity_weight (float): Вес сходства с вопросом. По умолчанию: 0.70.
        seed_similarity_weight (float): Вес сходства с seed. По умолчанию: 0.30.
        impact_citation_weight (float): Вес citations внутри impact. По умолчанию: 0.50.
        impact_recency_weight (float): Вес recency внутри impact. По умолчанию: 0.20.
        impact_pagerank_weight (float): Вес PageRank внутри impact. По умолчанию: 0.30.
        graph_distance_weight (float): Вес distance внутри graph score. По умолчанию: 0.60.
        graph_connectivity_weight (float): Вес connectivity. По умолчанию: 0.40.
        recency_tau (float): Параметр exponential recency decay. По умолчанию: 5.0.

    Fallbacks:
        Некорректные границы или сумма весов отклоняются при создании объекта.
    """

    max_depth: int = 2
    max_papers: int = 300
    top_k_expansion: int = 20
    min_year: int | None = None
    expand_references_topic_threshold: float = 0.75
    topic_weight: float = 0.60
    impact_weight: float = 0.25
    graph_weight: float = 0.15
    query_similarity_weight: float = 0.70
    seed_similarity_weight: float = 0.30
    impact_citation_weight: float = 0.50
    impact_recency_weight: float = 0.20
    impact_pagerank_weight: float = 0.30
    graph_distance_weight: float = 0.60
    graph_connectivity_weight: float = 0.40
    recency_tau: float = 5.0

    def __post_init__(self) -> None:
        """
        Проверяет ограничения research configuration.

        Returns:
            None: Валидный объект остаётся неизменным.

        Fallbacks:
            ValueError объясняет нарушенное ограничение.
        """

        # Validate hard expansion limits before a job can be enqueued.
        if self.max_depth < 1 or self.max_papers < 1 or self.top_k_expansion < 1:
            raise ValueError("Research limits must be positive")
        if self.recency_tau <= 0:
            raise ValueError("recency_tau must be positive")

        # Keep the three independent score components normalized.
        final_weights = (self.topic_weight, self.impact_weight, self.graph_weight)
        if any(weight < 0 for weight in final_weights):
            raise ValueError("Research score weights must be non-negative")
        total_weight = sum(final_weights)
        if abs(total_weight - 1.0) > 1e-9:
            raise ValueError("Research score weights must sum to 1")
        semantic_weights = (self.query_similarity_weight, self.seed_similarity_weight)
        if any(weight < 0 for weight in semantic_weights):
            raise ValueError("Semantic score weights must be non-negative")
        semantic_weight = sum(semantic_weights)
        if abs(semantic_weight - 1.0) > 1e-9:
            raise ValueError("Semantic score weights must sum to 1")

        # Keep impact signals independently normalized before final scoring.
        impact_weights = (
            self.impact_citation_weight,
            self.impact_recency_weight,
            self.impact_pagerank_weight,
        )
        if any(weight < 0 for weight in impact_weights):
            raise ValueError("Impact score weights must be non-negative")
        impact_weight = sum(impact_weights)
        if abs(impact_weight - 1.0) > 1e-9:
            raise ValueError("Impact score weights must sum to 1")

        # Keep graph proximity and connectivity weights normalized.
        graph_weights = (self.graph_distance_weight, self.graph_connectivity_weight)
        if any(weight < 0 for weight in graph_weights):
            raise ValueError("Graph component weights must be non-negative")
        graph_component_weight = sum(graph_weights)
        if abs(graph_component_weight - 1.0) > 1e-9:
            raise ValueError("Graph component weights must sum to 1")


@dataclass(slots=True)
class ResearchQuestion:
    """
    Отдельный research question проекта.

    Attributes:
        project_id (UUID): Идентификатор проекта.
        text (str): Текст вопроса.
        id (UUID): Идентификатор вопроса.

    Fallbacks:
        Пустой текст отклоняется при создании.
    """

    project_id: UUID
    text: str
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        """
        Нормализует и проверяет текст вопроса.

        Returns:
            None: Текст сохраняется без крайних пробелов.

        Fallbacks:
            ValueError создаётся для пустого вопроса.
        """

        self.text = self.text.strip()
        if not self.text:
            raise ValueError("Research question must not be empty")


@dataclass(slots=True)
class ResearchProject:
    """
    Исследовательский проект с несколькими вопросами.

    Attributes:
        name (str): Пользовательское имя проекта.
        config (ResearchConfig): Настройки controlled expansion.
        questions (list[ResearchQuestion]): Вопросы проекта.
        id (UUID): Идентификатор проекта.

    Fallbacks:
        Пустое имя отклоняется при создании.
    """

    name: str
    config: ResearchConfig = field(default_factory=ResearchConfig)
    questions: list[ResearchQuestion] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        """
        Нормализует и проверяет имя проекта.

        Returns:
            None: Имя сохраняется без крайних пробелов.

        Fallbacks:
            ValueError создаётся для пустого имени.
        """

        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Research project name must not be empty")
