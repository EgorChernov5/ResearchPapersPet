from unittest.mock import AsyncMock, Mock

import pytest
from app.domain.paper import ProviderPaper
from app.domain.related_work import PaperIdentityInput
from app.providers.base import ScholarlyPaperNotFoundError, ScholarlyProvider
from app.research.seed_resolution import SeedResolver


@pytest.mark.parametrize(
    ("source", "method", "identifier"),
    [
        (
            "https://www.semanticscholar.org/paper/title/0123456789abcdef0123456789abcdef01234567",
            "semantic_scholar_id",
            "0123456789abcdef0123456789abcdef01234567",
        ),
        ("https://doi.org/10.1000/test.1", "doi", "DOI:10.1000/test.1"),
        ("https://arxiv.org/abs/2405.14486", "arxiv", "ARXIV:2405.14486"),
        ("https://aclanthology.org/2024.findings-acl.886/", "acl", "ACL:2024.findings-acl.886"),
    ],
)
def test_extract_identifier(source: str, method: str, identifier: str) -> None:
    """
    Проверяет локальное извлечение canonical identifiers из URL.

    Parameters:
        source (str): Исходный URL.
        method (str): Ожидаемый resolution method.
        identifier (str): Ожидаемый prefixed identifier.

    Returns:
        None: Assertions подтверждают deterministic extraction.

    Fallbacks:
        Test failure предотвращает отправку произвольного URL в API.
    """

    provider = Mock(spec=ScholarlyProvider)
    assert SeedResolver(provider).extract_identifier(source) == (method, identifier)


@pytest.mark.asyncio
async def test_resolve_seed_by_doi_with_validation() -> None:
    """
    Проверяет canonical DOI lookup и title/year validation.

    Returns:
        None: Assertions подтверждают resolved DTO и confidence.

    Fallbacks:
        Test failure показывает нарушение приоритета identifier lookup.
    """

    # Return recorded provider metadata without any live API dependency.
    provider = Mock(spec=ScholarlyProvider)
    provider.get_paper = AsyncMock(
        return_value=ProviderPaper(
            paper_id="s2-paper-1",
            title="Fact or Fiction: Verifying Scientific Claims",
            year=2020,
            external_ids={"doi": "10.1000/scifact"},
        )
    )
    provider.search_papers = AsyncMock(return_value=[])
    identity = PaperIdentityInput(
        local_id="RW02",
        title="Fact or Fiction: Verifying Scientific Claims",
        year=2020,
        source="https://doi.org/10.1000/scifact",
    )

    result = await SeedResolver(provider).resolve_seed_papers([identity])

    assert not result.failures
    assert result.resolved[0].semantic_scholar_id == "s2-paper-1"
    assert result.resolved[0].resolution_method == "doi"
    assert result.resolved[0].resolution_confidence == 1.0
    provider.get_paper.assert_awaited_once_with("DOI:10.1000/scifact")
    provider.search_papers.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_id_result_falls_back_to_exact_title_search() -> None:
    """
    Проверяет validation даже после успешного exact ID response.

    Returns:
        None: Assertions подтверждают отказ от неверной ID article.

    Fallbacks:
        Title search используется, если provider ID metadata несовместимы.
    """

    # Simulate a wrong DOI match followed by a correct title match.
    provider = Mock(spec=ScholarlyProvider)
    provider.get_paper = AsyncMock(
        return_value=ProviderPaper(
            paper_id="wrong",
            title="Completely Different Work",
            year=1999,
            external_ids={},
        )
    )
    provider.search_papers = AsyncMock(
        return_value=[
            ProviderPaper(
                paper_id="correct",
                title="Expected Scientific Paper",
                year=2024,
                external_ids={},
            )
        ]
    )
    identity = PaperIdentityInput(
        local_id="RW03",
        title="Expected Scientific Paper",
        year=2024,
        source="DOI:10.1000/wrong",
    )

    result = await SeedResolver(provider).resolve_seed_papers([identity])

    assert result.resolved[0].paper_id == "correct"
    assert result.resolved[0].resolution_method == "title_search"


@pytest.mark.asyncio
async def test_unresolved_seed_does_not_stop_batch() -> None:
    """
    Проверяет per-paper failure isolation в одном batch.

    Returns:
        None: Assertions подтверждают один failure и один success.

    Fallbacks:
        Unresolved seed не скрывается и не прерывает следующий seed.
    """

    # Sequence covers failed exact lookup, two search fallbacks, then a second seed success.
    provider = Mock(spec=ScholarlyProvider)
    provider.get_paper = AsyncMock(side_effect=ScholarlyPaperNotFoundError("not found"))
    resolved_paper = ProviderPaper(
        paper_id="resolved",
        title="Resolvable Paper",
        year=2022,
        external_ids={},
    )
    provider.search_papers = AsyncMock(side_effect=[[], [], [resolved_paper]])
    identities = [
        PaperIdentityInput("RW01", "Missing Paper", 2020, "ARXIV:2001.00001"),
        PaperIdentityInput("RW02", "Resolvable Paper", 2022, None),
    ]

    result = await SeedResolver(provider).resolve_seed_papers(identities)

    assert [paper.local_id for paper in result.resolved] == ["RW02"]
    assert [failure.local_id for failure in result.failures] == ["RW01"]
    assert "passed title and year validation" in result.failures[0].reason


@pytest.mark.asyncio
async def test_duplicate_resolved_seed_is_reported() -> None:
    """
    Проверяет deduplication canonical seed papers.

    Returns:
        None: Assertions подтверждают один success и один duplicate failure.

    Fallbacks:
        Duplicate Related Work references не создают вторую global paper.
    """

    # Two different rows intentionally resolve to the same canonical paper ID.
    provider = Mock(spec=ScholarlyProvider)
    paper = ProviderPaper(
        paper_id="same-paper",
        title="Canonical Paper",
        year=2023,
        external_ids={},
    )
    provider.get_paper = AsyncMock()
    provider.search_papers = AsyncMock(side_effect=[[paper], [paper]])
    identities = [
        PaperIdentityInput("RW01", "Canonical Paper", 2023, None),
        PaperIdentityInput("RW02", "Canonical Paper", 2023, None),
    ]

    result = await SeedResolver(provider).resolve_seed_papers(identities)

    assert len(result.resolved) == 1
    assert len(result.failures) == 1
    assert "Duplicate seed" in result.failures[0].reason
