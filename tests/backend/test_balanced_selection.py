from uuid import UUID

from app.research.balanced_selection import BalancedPaperSelector
from app.research.structures import (
    PreliminaryCandidateScore,
    PreliminaryQuestionShortlist,
    PreliminaryScoringResult,
)


def test_one_question_matches_regular_top_k() -> None:
    """
    Проверяет обычный top-K для единственного research question.

    Returns:
        None: Selector сохраняет ranked порядок shortlist до лимита.

    Fallbacks:
        Кандидаты после глобального лимита не выбираются.
    """

    # Build one ranked shortlist whose size exceeds the global limit.
    question_id = UUID("00000000-0000-0000-0000-000000000010")
    paper_ids = [
        UUID("00000000-0000-0000-0000-000000000001"),
        UUID("00000000-0000-0000-0000-000000000002"),
        UUID("00000000-0000-0000-0000-000000000003"),
    ]
    result = PreliminaryScoringResult(
        [
            PreliminaryQuestionShortlist(
                question_id,
                [
                    PreliminaryCandidateScore(paper_ids[0], question_id, 0.9, 0.8, 0.87),
                    PreliminaryCandidateScore(paper_ids[1], question_id, 0.8, 0.7, 0.77),
                    PreliminaryCandidateScore(paper_ids[2], question_id, 0.7, 0.6, 0.67),
                ],
            )
        ]
    )

    # Select the same first two papers as a regular top-K operation.
    assert BalancedPaperSelector().select(result, 2) == paper_ids[:2]


def test_disjoint_shortlists_represent_every_question_at_exact_limit() -> None:
    """
    Проверяет представительство вопросов с непересекающимися кандидатами.

    Returns:
        None: При limit равном числу вопросов выбран один paper на вопрос.

    Fallbacks:
        Порядок вопросов задаёт первый round-robin проход.
    """

    # Give every question a distinct best candidate and an unused fallback.
    first_question = UUID("00000000-0000-0000-0000-000000000010")
    second_question = UUID("00000000-0000-0000-0000-000000000020")
    first_paper = UUID("00000000-0000-0000-0000-000000000001")
    second_paper = UUID("00000000-0000-0000-0000-000000000002")
    result = PreliminaryScoringResult(
        [
            PreliminaryQuestionShortlist(
                first_question,
                [
                    PreliminaryCandidateScore(first_paper, first_question, 0.9, 0.9, 0.9),
                    PreliminaryCandidateScore(
                        UUID("00000000-0000-0000-0000-000000000003"),
                        first_question,
                        0.8,
                        0.8,
                        0.8,
                    ),
                ],
            ),
            PreliminaryQuestionShortlist(
                second_question,
                [
                    PreliminaryCandidateScore(second_paper, second_question, 0.7, 0.7, 0.7),
                    PreliminaryCandidateScore(
                        UUID("00000000-0000-0000-0000-000000000004"),
                        second_question,
                        0.6,
                        0.6,
                        0.6,
                    ),
                ],
            ),
        ]
    )

    # Preserve both questions even though the second paper has a lower score.
    assert BalancedPaperSelector().select(result, 2) == [first_paper, second_paper]


def test_overlapping_shortlists_are_deduplicated_and_vacancies_are_filled() -> None:
    """
    Проверяет дедупликацию общих papers и заполнение свободных мест.

    Returns:
        None: Результат содержит уникальные papers до доступного лимита.

    Fallbacks:
        Вопрос с уже выбранным лидером получает следующего уникального кандидата.
    """

    # Put the same strongest paper first for two different questions.
    first_question = UUID("00000000-0000-0000-0000-000000000010")
    second_question = UUID("00000000-0000-0000-0000-000000000020")
    shared_paper = UUID("00000000-0000-0000-0000-000000000001")
    second_representative = UUID("00000000-0000-0000-0000-000000000002")
    best_remaining = UUID("00000000-0000-0000-0000-000000000003")
    result = PreliminaryScoringResult(
        [
            PreliminaryQuestionShortlist(
                first_question,
                [
                    PreliminaryCandidateScore(shared_paper, first_question, 0.95, 0.95, 0.95),
                    PreliminaryCandidateScore(best_remaining, first_question, 0.9, 0.9, 0.9),
                ],
            ),
            PreliminaryQuestionShortlist(
                second_question,
                [
                    PreliminaryCandidateScore(shared_paper, second_question, 0.99, 0.99, 0.99),
                    PreliminaryCandidateScore(
                        second_representative, second_question, 0.7, 0.7, 0.7
                    ),
                ],
            ),
        ]
    )

    # Skip the duplicate, represent question two, then fill by the best remaining score.
    selected = BalancedPaperSelector().select(result, 3)
    assert selected == [shared_paper, second_representative, best_remaining]
    assert len(selected) == len(set(selected)) == 3


def test_global_limit_is_never_exceeded_when_questions_outnumber_slots() -> None:
    """
    Проверяет жёсткое соблюдение глобального лимита selector.

    Returns:
        None: Число выбранных papers не превышает top_k_expansion.

    Fallbacks:
        Представительство всех вопросов невозможно при недостаточном лимите.
    """

    # Supply three independent questions but only two global slots.
    shortlists = []
    expected = []
    for value in range(1, 4):
        question_id = UUID(f"00000000-0000-0000-0000-{value + 10:012d}")
        paper_id = UUID(f"00000000-0000-0000-0000-{value:012d}")
        shortlists.append(
            PreliminaryQuestionShortlist(
                question_id,
                [PreliminaryCandidateScore(paper_id, question_id, 1.0, 1.0, 1.0)],
            )
        )
        expected.append(paper_id)

    # Stop the first round immediately when the global limit is reached.
    selected = BalancedPaperSelector().select(PreliminaryScoringResult(shortlists), 2)
    assert selected == expected[:2]
    assert len(selected) <= 2


def test_equal_scores_use_canonical_paper_id_and_repeat_deterministically() -> None:
    """
    Проверяет tie-breaker и повторяемость выбора на одинаковом входе.

    Returns:
        None: Равные scores упорядочены по canonical paper ID.

    Fallbacks:
        None score располагается после всех доступных числовых scores.
    """

    # Deliberately reverse equal-score inputs to exercise the canonical ID tie-breaker.
    question_id = UUID("00000000-0000-0000-0000-000000000010")
    lower_id = UUID("00000000-0000-0000-0000-000000000001")
    higher_id = UUID("00000000-0000-0000-0000-000000000002")
    missing_id = UUID("00000000-0000-0000-0000-000000000003")
    result = PreliminaryScoringResult(
        [
            PreliminaryQuestionShortlist(
                question_id,
                [
                    PreliminaryCandidateScore(higher_id, question_id, 0.8, 0.8, 0.8),
                    PreliminaryCandidateScore(lower_id, question_id, 0.8, 0.8, 0.8),
                    PreliminaryCandidateScore(missing_id, question_id, None, None, None),
                ],
            )
        ]
    )
    selector = BalancedPaperSelector()

    # Repeat selection and require byte-for-byte equivalent ordering.
    first_run = selector.select(result, 3)
    second_run = selector.select(result, 3)
    assert first_run == [lower_id, higher_id, missing_id]
    assert second_run == first_run
