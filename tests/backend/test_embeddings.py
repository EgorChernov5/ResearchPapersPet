from unittest.mock import Mock
from uuid import uuid4

import pytest
from app.domain.paper import Paper
from app.domain.project import ResearchQuestion
from app.research.embeddings import EmbeddingService


def test_embedding_service_encodes_title_and_optional_abstract() -> None:
    """
    Проверяет общий model space и title-only fallback для статьи.

    Returns:
        None: Assertions подтверждают vectors и входной scientific text.

    Fallbacks:
        Отсутствующий abstract не превращается в zero vector.
    """

    # Return one deterministic normalized vector per input text.
    encoder = Mock()
    encoder.get_sentence_embedding_dimension.return_value = 3
    encoder.encode.side_effect = lambda texts, **kwargs: [[1.0, 0.0, 0.0] for _ in texts]
    service = EmbeddingService("fixture", "1", 3, 8, encoder)
    paper = Paper(id=uuid4(), title="Paper without abstract")
    question = ResearchQuestion(
        id=uuid4(),
        project_id=uuid4(),
        text="What is the contribution?",
    )

    # Encode papers and questions through the same injected model.
    paper_batch = service.embed_papers([paper])
    question_batch = service.embed_questions([question])

    assert paper_batch.failures == []
    assert paper_batch.embeddings[0].vector == [1.0, 0.0, 0.0]
    assert question_batch.failures == []
    assert encoder.encode.call_args_list[0].args[0] == ["Paper without abstract [SEP] "]


def test_embedding_service_isolates_failed_paper() -> None:
    """
    Проверяет индивидуальный retry после ошибки batch inference.

    Returns:
        None: Успешная статья сохранена, ошибочная отражена в failures.

    Fallbacks:
        Ошибка одной статьи не удаляет embedding другой статьи batch.
    """

    # Fail the batch, recover the first paper, and fail only the second retry.
    encoder = Mock()
    encoder.get_sentence_embedding_dimension.return_value = 2
    encoder.encode.side_effect = [
        RuntimeError("batch failure"),
        [[0.0, 1.0]],
        RuntimeError("paper failure"),
    ]
    service = EmbeddingService("fixture", "1", 2, 2, encoder)
    first = Paper(id=uuid4(), title="First")
    second = Paper(id=uuid4(), title="Second")

    result = service.embed_papers([first, second])

    assert [embedding.paper_id for embedding in result.embeddings] == [first.id]
    assert result.embeddings[0].vector == [0.0, 1.0]
    assert [failure.entity_id for failure in result.failures] == [second.id]
    assert result.failures[0].reason == "paper failure"


def test_embedding_service_rejects_model_dimension_mismatch() -> None:
    """
    Проверяет защиту versioned vector contract от неверной модели.

    Returns:
        None: Assertion подтверждает понятную ошибку размерности.

    Fallbacks:
        Несовместимый encoder отклоняется до persistence.
    """

    # Report a model dimension different from the database contract.
    encoder = Mock()
    encoder.get_sentence_embedding_dimension.return_value = 2
    service = EmbeddingService("fixture", "1", 3, 1, encoder)

    with pytest.raises(ValueError, match="returns 2 dimensions; configured 3"):
        service.embed_texts(["text"])
