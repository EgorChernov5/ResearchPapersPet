from math import exp, log1p

from app.domain.paper import Paper
from app.domain.scoring import PaperGraphMetrics, PaperImpactScore


class ImpactRanker:
    """
    Рассчитывает citation, recency, PageRank и aggregated impact scores.

    Attributes:
        recency_tau (float): Параметр exponential age decay.
        citation_weight (float): Вес normalized citations.
        recency_weight (float): Вес recency.
        pagerank_weight (float): Вес PageRank.

    Fallbacks:
        Missing metadata исключаются из среднего с перераспределением веса.
    """

    def __init__(
        self,
        recency_tau: float,
        citation_weight: float,
        recency_weight: float,
        pagerank_weight: float,
    ) -> None:
        """
        Настраивает impact scoring.

        Parameters:
            recency_tau (float): Положительная константа age decay.
            citation_weight (float): Вес citation score.
            recency_weight (float): Вес recency score.
            pagerank_weight (float): Вес PageRank score.

        Returns:
            None: Метод сохраняет валидные параметры.

        Fallbacks:
            Отрицательные или полностью нулевые weights отклоняются.
        """

        if recency_tau <= 0:
            raise ValueError("recency_tau must be positive")
        weights = (citation_weight, recency_weight, pagerank_weight)
        if any(weight < 0 for weight in weights) or sum(weights) <= 0:
            raise ValueError("Impact weights must be non-negative and non-zero")
        self.recency_tau = recency_tau
        self.citation_weight = citation_weight
        self.recency_weight = recency_weight
        self.pagerank_weight = pagerank_weight

    def rank(
        self,
        papers: list[Paper],
        graph_metrics: list[PaperGraphMetrics],
        current_year: int,
    ) -> list[PaperImpactScore]:
        """
        Рассчитывает impact scores для project papers.

        Parameters:
            papers (list[Paper]): Глобальные metadata статей проекта.
            graph_metrics (list[PaperGraphMetrics]): Project PageRank metrics.
            current_year (int): Год, относительно которого считается recency.

        Returns:
            list[PaperImpactScore]: Impact-компоненты в порядке papers.

        Fallbacks:
            Missing year, citation count или graph metric сохраняются как None.
        """

        # Normalize log citation counts by the strongest available paper.
        citation_values = {
            paper.id: log1p(max(paper.citation_count, 0))
            for paper in papers
            if paper.citation_count is not None
        }
        max_citation_value = max(citation_values.values(), default=0.0)
        metrics_by_paper = {metric.paper_id: metric for metric in graph_metrics}

        # Calculate available components and renormalize only their active weights.
        results = []
        for paper in papers:
            raw_citation = citation_values.get(paper.id)
            if raw_citation is None:
                citation_score = None
            elif max_citation_value > 0:
                citation_score = raw_citation / max_citation_value
            else:
                citation_score = 0.0
            recency_score = (
                exp(-max(current_year - paper.year, 0) / self.recency_tau)
                if paper.year is not None
                else None
            )
            metric = metrics_by_paper.get(paper.id)
            pagerank_score = metric.pagerank_score if metric is not None else None
            available = [
                (citation_score, self.citation_weight),
                (recency_score, self.recency_weight),
                (pagerank_score, self.pagerank_weight),
            ]
            total_weight = sum(weight for value, weight in available if value is not None)
            impact_score = (
                sum(value * weight for value, weight in available if value is not None)
                / total_weight
                if total_weight > 0
                else None
            )
            results.append(
                PaperImpactScore(
                    paper_id=paper.id,
                    citation_score=citation_score,
                    recency_score=recency_score,
                    pagerank_score=pagerank_score,
                    impact_score=impact_score,
                )
            )
        return results
