from uuid import uuid4

import pytest
from app.domain.embedding import EmbeddedPaper, EmbeddedQuestion
from app.research.semantic_ranking import SemanticRanker


def test_semantic_ranker_combines_query_and_nearest_seed_similarity() -> None:
    """
    Проверяет cosine scores и взвешенный topic score.

    Returns:
        None: Assertions подтверждают pair-level и project-level агрегацию.

    Fallbacks:
        Nearest-seed similarity выбирается максимумом по seed embeddings.
    """

    # Build a seed, candidate, and orthogonal research question.
    seed_id = uuid4()
    candidate_id = uuid4()
    question_id = uuid4()
    papers = [
        EmbeddedPaper(seed_id, [1.0, 0.0]),
        EmbeddedPaper(candidate_id, [0.8, 0.6]),
    ]
    questions = [EmbeddedQuestion(question_id, [0.0, 1.0])]

    result = SemanticRanker(0.7, 0.3).rank(uuid4(), papers, questions, {seed_id})

    candidate = next(score for score in result.paper_scores if score.paper_id == candidate_id)
    pair = next(score for score in result.question_scores if score.paper_id == candidate_id)
    assert candidate.query_similarity == pytest.approx(0.6)
    assert candidate.seed_similarity == pytest.approx(0.8)
    assert candidate.topic_score == pytest.approx(0.66)
    assert pair.topic_score == pytest.approx(0.66)


def test_semantic_ranker_redistributes_weight_for_missing_component() -> None:
    """
    Проверяет отсутствие missing-as-zero bias без seed embeddings.

    Returns:
        None: Доступный query score получает полный нормализованный вес.

    Fallbacks:
        Полностью отсутствующие признаки возвращают None.
    """

    # Rank without seed papers so only question similarity is available.
    paper_id = uuid4()
    question_id = uuid4()
    ranker = SemanticRanker(0.7, 0.3)
    result = ranker.rank(
        uuid4(),
        [EmbeddedPaper(paper_id, [1.0, 0.0])],
        [EmbeddedQuestion(question_id, [1.0, 0.0])],
        set(),
    )

    assert result.paper_scores[0].seed_similarity is None
    assert result.paper_scores[0].topic_score == pytest.approx(1.0)
    assert (
        ranker.weighted_average_available(
            {"query_similarity": None, "seed_similarity": None},
            {"query_similarity": 0.7, "seed_similarity": 0.3},
        )
        is None
    )


def test_semantic_ranker_uses_best_research_question() -> None:
    """
    Проверяет max aggregation при нескольких research questions.

    Returns:
        None: Project-level relevance совпадает с лучшим вопросом.

    Fallbacks:
        Pair-level оценки сохраняются для каждого вопроса отдельно.
    """

    # Provide two questions with different relevance to one paper.
    paper_id = uuid4()
    questions = [
        EmbeddedQuestion(uuid4(), [1.0, 0.0]),
        EmbeddedQuestion(uuid4(), [0.0, 1.0]),
    ]

    result = SemanticRanker(0.7, 0.3).rank(
        uuid4(),
        [EmbeddedPaper(paper_id, [1.0, 0.0])],
        questions,
        set(),
    )

    assert len(result.question_scores) == 2
    assert result.paper_scores[0].query_similarity == pytest.approx(1.0)
    assert result.paper_scores[0].topic_score == pytest.approx(1.0)
