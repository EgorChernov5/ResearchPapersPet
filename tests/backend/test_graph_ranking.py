from math import exp, log
from uuid import uuid4

import pytest
from app.domain.citation import Citation
from app.domain.paper import Paper
from app.domain.scoring import PaperGraphMetrics, PaperImpactScore, ProjectPaper
from app.research.final_scoring import FinalRanker
from app.research.graph_analysis import GraphAnalyzer
from app.research.impact_ranking import ImpactRanker


def test_graph_analyzer_builds_directed_metrics_and_seed_distances() -> None:
    """
    Проверяет directed degrees и undirected proximity до seed.

    Returns:
        None: Assertions подтверждают graph metrics для connected и isolated papers.

    Fallbacks:
        Изолированная статья получает missing distance, но остаётся в результате.
    """

    # Build both citation directions around one seed and retain an isolated paper.
    seed_id = uuid4()
    reference_id = uuid4()
    citing_id = uuid4()
    isolated_id = uuid4()
    citations = [
        Citation(source_paper_id=seed_id, target_paper_id=reference_id),
        Citation(source_paper_id=citing_id, target_paper_id=seed_id),
    ]

    result = GraphAnalyzer().analyze(
        {seed_id, reference_id, citing_id, isolated_id},
        citations,
        {seed_id},
    )
    metrics = {item.paper_id: item for item in result}

    assert metrics[seed_id].in_degree == 1
    assert metrics[seed_id].out_degree == 1
    assert metrics[seed_id].degree_centrality == pytest.approx(2 / 3)
    assert metrics[seed_id].distance_from_seed == 0
    assert metrics[seed_id].distance_score == pytest.approx(1.0)
    assert metrics[reference_id].distance_from_seed == 1
    assert metrics[citing_id].distance_from_seed == 1
    assert metrics[isolated_id].distance_from_seed is None
    assert metrics[isolated_id].connectivity_score == pytest.approx(0.0)
    assert max(item.pagerank_score for item in result) == pytest.approx(1.0)


def test_impact_ranker_normalizes_citations_and_redistributes_missing_values() -> None:
    """
    Проверяет citation normalization, recency decay и missing-value weighting.

    Returns:
        None: Assertions подтверждают impact components и fallback на PageRank.

    Fallbacks:
        Missing citation/year не становятся нулями внутри weighted average.
    """

    # Provide one complete paper and one paper with only a graph signal.
    complete_id = uuid4()
    missing_id = uuid4()
    papers = [
        Paper(id=complete_id, title="Complete", year=2020, citation_count=99),
        Paper(id=missing_id, title="Missing"),
    ]
    graph_metrics = [
        PaperGraphMetrics(complete_id, 1, 1, 1.0, 0, 1.0, 0.5, 1.0),
        PaperGraphMetrics(missing_id, 0, 0, 0.0, None, None, 0.0, 0.5),
    ]

    result = ImpactRanker(5.0, 0.5, 0.2, 0.3).rank(papers, graph_metrics, 2025)
    scores = {item.paper_id: item for item in result}

    assert scores[complete_id].citation_score == pytest.approx(log(100) / log(100))
    assert scores[complete_id].recency_score == pytest.approx(exp(-1))
    assert scores[complete_id].impact_score == pytest.approx(0.8 + 0.2 * exp(-1))
    assert scores[missing_id].citation_score is None
    assert scores[missing_id].recency_score is None
    assert scores[missing_id].impact_score == pytest.approx(0.5)


def test_final_ranker_combines_independent_components() -> None:
    """
    Проверяет graph score и итоговую формулу 0.60/0.25/0.15.

    Returns:
        None: Assertions подтверждают независимое weighted scoring.

    Fallbacks:
        Компоненты передаются как optional и поддерживают weight redistribution.
    """

    # Combine deterministic semantic, impact, distance, and connectivity values.
    project_id = uuid4()
    paper_id = uuid4()
    missing_topic_id = uuid4()
    project_paper = ProjectPaper(project_id, paper_id, False, topic_score=0.8)
    missing_topic_paper = ProjectPaper(project_id, missing_topic_id, False)
    graph_metric = PaperGraphMetrics(paper_id, 1, 1, 1.0, 1, 0.5, 0.25, 0.7)
    missing_distance_metric = PaperGraphMetrics(
        missing_topic_id,
        0,
        0,
        0.0,
        None,
        None,
        0.4,
        0.2,
    )
    impact_score = PaperImpactScore(paper_id, 0.5, 0.6, 0.7, 0.6)
    missing_metadata_impact = PaperImpactScore(missing_topic_id, None, None, 0.2, 0.2)

    result = FinalRanker(0.60, 0.25, 0.15, 0.60, 0.40).rank(
        [project_paper, missing_topic_paper],
        [graph_metric, missing_distance_metric],
        [impact_score, missing_metadata_impact],
    )
    scores = {item.paper_id: item for item in result}

    assert scores[paper_id].graph_score == pytest.approx(0.4)
    assert scores[paper_id].final_score == pytest.approx(0.69)
    assert scores[paper_id].pagerank_score == pytest.approx(0.7)
    assert scores[missing_topic_id].graph_score == pytest.approx(0.4)
    assert scores[missing_topic_id].final_score == pytest.approx(0.275)
