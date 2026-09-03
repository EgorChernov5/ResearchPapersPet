from app.domain.scoring import (
    PaperFinalScore,
    PaperGraphMetrics,
    PaperImpactScore,
    ProjectPaper,
)


class FinalRanker:
    """
    Объединяет semantic, impact и graph components в final project score.

    Attributes:
        topic_weight (float): Вес semantic relevance.
        impact_weight (float): Вес impact score.
        graph_weight (float): Вес graph score.

    Fallbacks:
        Missing components исключаются с перераспределением доступных весов.
    """

    def __init__(
        self,
        topic_weight: float,
        impact_weight: float,
        graph_weight: float,
        distance_weight: float,
        connectivity_weight: float,
    ) -> None:
        """
        Настраивает graph и final scoring weights.

        Parameters:
            topic_weight (float): Вес topic score.
            impact_weight (float): Вес impact score.
            graph_weight (float): Вес graph score.
            distance_weight (float): Вес distance score внутри graph score.
            connectivity_weight (float): Вес connectivity внутри graph score.

        Returns:
            None: Метод сохраняет валидные weights.

        Fallbacks:
            Negative и полностью нулевые группы weights отклоняются.
        """

        final_weights = (topic_weight, impact_weight, graph_weight)
        graph_weights = (distance_weight, connectivity_weight)
        if any(weight < 0 for weight in final_weights) or sum(final_weights) <= 0:
            raise ValueError("Final weights must be non-negative and non-zero")
        if any(weight < 0 for weight in graph_weights) or sum(graph_weights) <= 0:
            raise ValueError("Graph weights must be non-negative and non-zero")
        self.topic_weight = topic_weight
        self.impact_weight = impact_weight
        self.graph_weight = graph_weight
        self.distance_weight = distance_weight
        self.connectivity_weight = connectivity_weight

    def rank(
        self,
        project_papers: list[ProjectPaper],
        graph_metrics: list[PaperGraphMetrics],
        impact_scores: list[PaperImpactScore],
    ) -> list[PaperFinalScore]:
        """
        Рассчитывает graph и final scores каждой project paper.

        Parameters:
            project_papers (list[ProjectPaper]): Project-specific semantic state.
            graph_metrics (list[PaperGraphMetrics]): Structural metrics.
            impact_scores (list[PaperImpactScore]): Impact components.

        Returns:
            list[PaperFinalScore]: Полные ranking results.

        Fallbacks:
            Paper без graph или impact result сохраняет соответствующие поля как None.
        """

        # Index stage outputs by the shared global paper identifier.
        metrics_by_paper = {metric.paper_id: metric for metric in graph_metrics}
        impacts_by_paper = {score.paper_id: score for score in impact_scores}
        results = []

        # Calculate graph first, then combine independent final components.
        for project_paper in project_papers:
            metric = metrics_by_paper.get(project_paper.paper_id)
            impact = impacts_by_paper.get(project_paper.paper_id)
            graph_values = [
                (metric.distance_score if metric is not None else None, self.distance_weight),
                (
                    metric.connectivity_score if metric is not None else None,
                    self.connectivity_weight,
                ),
            ]
            graph_total_weight = sum(weight for value, weight in graph_values if value is not None)
            graph_score = (
                sum(value * weight for value, weight in graph_values if value is not None)
                / graph_total_weight
                if graph_total_weight > 0
                else None
            )
            final_values = [
                (project_paper.topic_score, self.topic_weight),
                (impact.impact_score if impact is not None else None, self.impact_weight),
                (graph_score, self.graph_weight),
            ]
            final_total_weight = sum(weight for value, weight in final_values if value is not None)
            final_score = (
                sum(value * weight for value, weight in final_values if value is not None)
                / final_total_weight
                if final_total_weight > 0
                else None
            )
            results.append(
                PaperFinalScore(
                    paper_id=project_paper.paper_id,
                    citation_score=impact.citation_score if impact is not None else None,
                    recency_score=impact.recency_score if impact is not None else None,
                    impact_score=impact.impact_score if impact is not None else None,
                    distance_score=metric.distance_score if metric is not None else None,
                    connectivity_score=metric.connectivity_score if metric is not None else None,
                    pagerank_score=metric.pagerank_score if metric is not None else None,
                    graph_score=graph_score,
                    final_score=final_score,
                )
            )
        return results
