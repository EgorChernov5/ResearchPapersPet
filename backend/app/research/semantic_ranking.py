from math import sqrt
from uuid import UUID

from app.domain.embedding import (
    EmbeddedPaper,
    EmbeddedQuestion,
    PaperSemanticScore,
    SemanticRankingResult,
)
from app.domain.scoring import ProjectPaperQuestionScore


class SemanticRanker:
    """
    Рассчитывает query, seed и topic similarity без missing-as-zero.

    Attributes:
        query_weight (float): Вес question similarity.
        seed_weight (float): Вес similarity к ближайшему seed.

    Fallbacks:
        Missing или zero-norm vector даёт None и перераспределяет доступные веса.
    """

    def __init__(self, query_weight: float, seed_weight: float) -> None:
        """
        Настраивает semantic topic weights.

        Parameters:
            query_weight (float): Вес question similarity.
            seed_weight (float): Вес seed similarity.

        Returns:
            None: Метод инициализирует ranker.

        Fallbacks:
            Negative weights и zero total отклоняются ValueError.
        """

        if query_weight < 0 or seed_weight < 0 or query_weight + seed_weight <= 0:
            raise ValueError("Semantic ranking weights must be non-negative and non-zero")
        self.query_weight = query_weight
        self.seed_weight = seed_weight

    def cosine_similarity(
        self,
        first: list[float],
        second: list[float],
    ) -> float | None:
        """
        Вычисляет cosine similarity двух compatible vectors.

        Parameters:
            first (list[float]): Первый embedding.
            second (list[float]): Второй embedding.

        Returns:
            float | None: Similarity от -1 до 1 или None для zero norm.

        Fallbacks:
            Разная размерность отклоняется ValueError.
        """

        if len(first) != len(second):
            raise ValueError("Cosine vectors must have equal dimensions")
        first_norm = sqrt(sum(value * value for value in first))
        second_norm = sqrt(sum(value * value for value in second))
        if first_norm == 0 or second_norm == 0:
            return None
        similarity = sum(left * right for left, right in zip(first, second, strict=True))
        return max(min(similarity / (first_norm * second_norm), 1.0), -1.0)

    def weighted_average_available(
        self,
        values: dict[str, float | None],
        weights: dict[str, float],
    ) -> float | None:
        """
        Усредняет только доступные признаки с перераспределением weights.

        Parameters:
            values (dict[str, float | None]): Named optional features.
            weights (dict[str, float]): Configured feature weights.

        Returns:
            float | None: Weighted average или None без доступных features.

        Fallbacks:
            Missing value не интерпретируется как zero.
        """

        available = {
            name: value
            for name, value in values.items()
            if value is not None and weights.get(name, 0.0) > 0
        }
        total_weight = sum(weights[name] for name in available)
        if not available or total_weight <= 0:
            return None
        return sum(available[name] * weights[name] for name in available) / total_weight

    def rank(
        self,
        project_id: UUID,
        papers: list[EmbeddedPaper],
        questions: list[EmbeddedQuestion],
        seed_paper_ids: set[UUID],
    ) -> SemanticRankingResult:
        """
        Рассчитывает pair-level и max-aggregated project scores.

        Parameters:
            project_id (UUID): Идентификатор исследовательского проекта.
            papers (list[EmbeddedPaper]): Доступные paper embeddings.
            questions (list[EmbeddedQuestion]): Доступные question embeddings.
            seed_paper_ids (set[UUID]): Global IDs seed papers.

        Returns:
            SemanticRankingResult: Pair и project-level scores.

        Fallbacks:
            Без seed embeddings topic score использует только query similarity.
        """

        result = SemanticRankingResult()
        seed_vectors = [paper.vector for paper in papers if paper.paper_id in seed_paper_ids]
        for paper in papers:
            seed_similarities = [
                self.cosine_similarity(paper.vector, vector) for vector in seed_vectors
            ]
            seed_similarity = max(
                (value for value in seed_similarities if value is not None),
                default=None,
            )
            query_similarities = []
            question_topic_scores = []
            for question in questions:
                query_similarity = self.cosine_similarity(paper.vector, question.vector)
                topic_score = self.weighted_average_available(
                    {
                        "query_similarity": query_similarity,
                        "seed_similarity": seed_similarity,
                    },
                    {
                        "query_similarity": self.query_weight,
                        "seed_similarity": self.seed_weight,
                    },
                )
                result.question_scores.append(
                    ProjectPaperQuestionScore(
                        project_id=project_id,
                        paper_id=paper.paper_id,
                        question_id=question.question_id,
                        query_similarity=query_similarity,
                        topic_score=topic_score,
                    )
                )
                if query_similarity is not None:
                    query_similarities.append(query_similarity)
                if topic_score is not None:
                    question_topic_scores.append(topic_score)
            result.paper_scores.append(
                PaperSemanticScore(
                    paper_id=paper.paper_id,
                    query_similarity=max(query_similarities, default=None),
                    seed_similarity=seed_similarity,
                    topic_score=max(question_topic_scores, default=None),
                )
            )
        return result
