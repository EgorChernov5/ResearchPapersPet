from dataclasses import fields
from unittest.mock import Mock
from uuid import uuid4

import pytest
from app.domain.embedding import EmbeddedPaper, EmbeddedQuestion
from app.domain.paper import Paper
from app.domain.project import ResearchQuestion
from app.repositories.embeddings import EmbeddingRepository
from app.research.embeddings import EmbeddingService
from app.research.preliminary_scoring import (
    PreliminaryScoringService,
    PreliminarySemanticScorer,
)
from app.research.structures import PreliminaryCandidateScore


def test_preliminary_scorer_calculates_formula_missing_values_and_sorting() -> None:
    """
    Проверяет реальную формулу, missing policy и сортировку controlled vectors.

    Returns:
        None: Shortlist отсортирован по preliminary topic score.

    Fallbacks:
        Zero-norm vector остаётся последним с None вместо искусственного zero score.
    """

    # Score three controlled vectors against one question and one seed.
    best_id = uuid4()
    mixed_id = uuid4()
    missing_id = uuid4()
    question_id = uuid4()
    result = PreliminarySemanticScorer(0.7, 0.3).rank(
        [
            EmbeddedPaper(mixed_id, [0.8, 0.6]),
            EmbeddedPaper(missing_id, [0.0, 0.0]),
            EmbeddedPaper(best_id, [0.0, 1.0]),
        ],
        [EmbeddedQuestion(question_id, [0.0, 1.0])],
        [EmbeddedPaper(uuid4(), [1.0, 0.0])],
        3,
    )

    shortlist = result.shortlists[0]
    assert shortlist.question_id == question_id
    assert [score.paper_id for score in shortlist.candidates] == [best_id, mixed_id, missing_id]
    assert shortlist.candidates[0].preliminary_topic_score == pytest.approx(0.7)
    assert shortlist.candidates[1].query_similarity == pytest.approx(0.6)
    assert shortlist.candidates[1].seed_similarity == pytest.approx(0.8)
    assert shortlist.candidates[1].preliminary_topic_score == pytest.approx(0.66)
    assert shortlist.candidates[2].preliminary_topic_score is None


def test_preliminary_scorer_builds_independent_question_shortlists() -> None:
    """
    Проверяет независимое ранжирование одного candidate pool по нескольким вопросам.

    Returns:
        None: Каждый вопрос получает собственный порядок кандидатов.

    Fallbacks:
        Отсутствие seed vectors переносит полный вес на query similarity.
    """

    # Use orthogonal candidates so each question has a different best paper.
    first_id = uuid4()
    second_id = uuid4()
    first_question_id = uuid4()
    second_question_id = uuid4()
    result = PreliminarySemanticScorer(0.7, 0.3).rank(
        [EmbeddedPaper(first_id, [1.0, 0.0]), EmbeddedPaper(second_id, [0.0, 1.0])],
        [
            EmbeddedQuestion(first_question_id, [1.0, 0.0]),
            EmbeddedQuestion(second_question_id, [0.0, 1.0]),
        ],
        [],
        2,
    )

    assert [score.paper_id for score in result.shortlists[0].candidates] == [
        first_id,
        second_id,
    ]
    assert [score.paper_id for score in result.shortlists[1].candidates] == [
        second_id,
        first_id,
    ]
    assert all(
        score.seed_similarity is None
        for shortlist in result.shortlists
        for score in shortlist.candidates
    )


def test_preliminary_result_excludes_impact_and_graph_signals() -> None:
    """
    Проверяет узкий контракт результата до graph expansion.

    Returns:
        None: DTO не содержит citations, recency или graph metrics.

    Fallbacks:
        Новые final-ranking поля требуют отдельного изменения контракта.
    """

    # Guard the preliminary DTO from accidental final-ranking signal leakage.
    assert {field.name for field in fields(PreliminaryCandidateScore)} == {
        "paper_id",
        "question_id",
        "query_similarity",
        "seed_similarity",
        "preliminary_topic_score",
    }


def test_preliminary_service_reuses_cached_papers_and_embeds_only_missing() -> None:
    """
    Проверяет versioned cache contract без подмены результата scorer.

    Returns:
        None: Encoder получает только отсутствующие paper metadata.

    Fallbacks:
        Research questions кодируются при каждом project-specific scoring request.
    """

    # Return one cached candidate while the encoder creates a missing seed vector.
    cached = Paper(id=uuid4(), title="Cached candidate")
    seed = Paper(id=uuid4(), title="Missing seed")
    question = ResearchQuestion(project_id=uuid4(), text="Cached candidate?")
    repository = Mock(spec=EmbeddingRepository)
    repository.get_many.return_value = [EmbeddedPaper(cached.id, [1.0, 0.0])]
    encoder = Mock()
    encoder.get_embedding_dimension.return_value = 2
    encoder.encode.side_effect = [[[1.0, 0.0]], [[1.0, 0.0]]]
    embedding_service = EmbeddingService("fixture", "v1", 2, 8, encoder)
    service = PreliminaryScoringService(
        embedding_service,
        repository,
        PreliminarySemanticScorer(0.7, 0.3),
    )

    result = service.rank([cached], [seed], [question], 1)

    assert encoder.encode.call_args_list[0].args[0] == ["Missing seed"]
    assert encoder.encode.call_args_list[1].args[0] == ["Cached candidate?"]
    repository.upsert.assert_called_once()
    assert repository.upsert.call_args.args[0].paper_id == seed.id
    assert result.shortlists[0].candidates[0].paper_id == cached.id
