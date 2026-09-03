from dataclasses import dataclass, field
from uuid import UUID

from app.domain.scoring import ProjectPaperQuestionScore


@dataclass(slots=True)
class EmbeddedPaper:
    """
    Paper identifier и embedding в едином model space.

    Attributes:
        paper_id (UUID): Идентификатор global Paper.
        vector (list[float]): Нормализованный embedding vector.

    Fallbacks:
        Failed paper embedding хранится отдельно как EmbeddingFailure.
    """

    paper_id: UUID
    vector: list[float]


@dataclass(slots=True)
class EmbeddedQuestion:
    """
    Research question identifier и embedding.

    Attributes:
        question_id (UUID): Идентификатор ResearchQuestion.
        vector (list[float]): Нормализованный embedding vector.

    Fallbacks:
        Failed question embedding хранится отдельно как EmbeddingFailure.
    """

    question_id: UUID
    vector: list[float]


@dataclass(slots=True)
class EmbeddingFailure:
    """
    Изолированная ошибка embedding одной domain entity.

    Attributes:
        entity_id (UUID): Идентификатор paper или question.
        reason (str): Понятная причина model failure.

    Fallbacks:
        Failure не превращается в zero vector.
    """

    entity_id: UUID
    reason: str


@dataclass(slots=True)
class PaperEmbeddingBatch:
    """
    Результат batched paper embedding.

    Attributes:
        embeddings (list[EmbeddedPaper]): Успешные vectors.
        failures (list[EmbeddingFailure]): Изолированные errors.

    Fallbacks:
        Полностью неуспешный batch возвращает пустой embeddings.
    """

    embeddings: list[EmbeddedPaper] = field(default_factory=list)
    failures: list[EmbeddingFailure] = field(default_factory=list)


@dataclass(slots=True)
class QuestionEmbeddingBatch:
    """
    Результат batched research question embedding.

    Attributes:
        embeddings (list[EmbeddedQuestion]): Успешные vectors.
        failures (list[EmbeddingFailure]): Изолированные errors.

    Fallbacks:
        Полностью неуспешный batch возвращает пустой embeddings.
    """

    embeddings: list[EmbeddedQuestion] = field(default_factory=list)
    failures: list[EmbeddingFailure] = field(default_factory=list)


@dataclass(slots=True)
class PaperSemanticScore:
    """
    Агрегированные project-level semantic scores статьи.

    Attributes:
        paper_id (UUID): Идентификатор global Paper.
        query_similarity (float | None): Max similarity по вопросам.
        seed_similarity (float | None): Max similarity по seeds.
        topic_score (float | None): Max topic score по вопросам.

    Fallbacks:
        Missing components остаются None и не интерпретируются как ноль.
    """

    paper_id: UUID
    query_similarity: float | None
    seed_similarity: float | None
    topic_score: float | None


@dataclass(slots=True)
class SemanticRankingResult:
    """
    Полный semantic-ranking результат проекта.

    Attributes:
        paper_scores (list[PaperSemanticScore]): Project-level scores.
        question_scores (list[ProjectPaperQuestionScore]): Pair-level scores.

    Fallbacks:
        Papers без embeddings отсутствуют в результате и сохраняют NULL scores.
    """

    paper_scores: list[PaperSemanticScore] = field(default_factory=list)
    question_scores: list[ProjectPaperQuestionScore] = field(default_factory=list)
