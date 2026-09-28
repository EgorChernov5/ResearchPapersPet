from unittest.mock import AsyncMock, Mock

import pytest
from app.domain.paper import ProviderPaper
from app.domain.project import ResearchConfig
from app.providers.base import ScholarlyProvider, ScholarlyProviderError
from app.research.discovery import CitationDiscovery


@pytest.mark.asyncio
async def test_discovery_builds_depth_one_edges_in_both_directions() -> None:
    """
    Проверяет references/citations semantics и depth=1.

    Returns:
        None: Assertions подтверждают papers и направленные edges.

    Fallbacks:
        Пустые optional metadata не мешают graph construction.
    """

    seed = ProviderPaper("seed", "Seed", {}, year=2024)
    reference = ProviderPaper("reference", "Reference", {}, year=2020, citation_count=10)
    citing = ProviderPaper("citing", "Citing", {}, year=2025, citation_count=20)
    provider = Mock(spec=ScholarlyProvider)
    provider.get_references = AsyncMock(return_value=[reference])
    provider.get_citations = AsyncMock(return_value=[citing])

    result = await CitationDiscovery(provider).discover(
        [seed],
        ResearchConfig(max_depth=1, max_papers=10, top_k_expansion=5),
    )

    assert [(item.paper.paper_id, item.depth) for item in result.papers] == [
        ("seed", 0),
        ("citing", 1),
        ("reference", 1),
    ]
    assert {(edge.source_paper_id, edge.target_paper_id) for edge in result.citations} == {
        ("seed", "reference"),
        ("citing", "seed"),
    }
    provider.get_references.assert_awaited_once_with("seed", limit=5)
    provider.get_citations.assert_awaited_once_with("seed", limit=5)


@pytest.mark.asyncio
async def test_discovery_isolates_provider_failure_and_respects_limits() -> None:
    """
    Проверяет per-direction failure isolation и MAX_PAPERS.

    Returns:
        None: Assertions подтверждают продолжение discovery после ошибки.

    Fallbacks:
        Ошибка references одного seed не удаляет seed и успешные citations.
    """

    first_seed = ProviderPaper("seed-1", "Seed One", {}, year=2024)
    second_seed = ProviderPaper("seed-2", "Seed Two", {}, year=2024)
    citing = ProviderPaper("citing", "Citing", {}, year=2025, citation_count=50)
    ignored = ProviderPaper("ignored", "Ignored", {}, year=2010, citation_count=100)
    provider = Mock(spec=ScholarlyProvider)
    provider.get_references = AsyncMock(side_effect=[ScholarlyProviderError("timeout"), [ignored]])
    provider.get_citations = AsyncMock(side_effect=[[citing], []])

    result = await CitationDiscovery(provider).discover(
        [first_seed, second_seed],
        ResearchConfig(
            max_depth=1,
            max_papers=3,
            top_k_expansion=2,
            min_year=2020,
        ),
    )

    assert [item.paper.paper_id for item in result.papers] == ["seed-1", "seed-2", "citing"]
    assert len(result.failures) == 1
    assert result.failures[0].paper_id == "seed-1"
    assert result.failures[0].direction == "references"


@pytest.mark.xfail(
    reason="Stage 4 will implement bounded multi-level citation traversal",
    strict=True,
)
@pytest.mark.asyncio
async def test_discovery_expands_each_frontier_until_max_depth() -> None:
    """
    Проверяет последовательное расширение citation graph до max_depth=2.

    Returns:
        None: Assertions подтверждают второй frontier, depths и направленные edges.

    Fallbacks:
        До этапа 4 тест остаётся явным strict xfail, а не скрытым skip.
    """

    # Build a linear reference chain so each frontier has one deterministic paper.
    seed = ProviderPaper("seed", "Seed", {}, year=2024)
    reference = ProviderPaper("reference", "Reference", {}, year=2023)
    second_level = ProviderPaper("second-level", "Second Level", {}, year=2022)
    provider = Mock(spec=ScholarlyProvider)
    provider.get_references = AsyncMock(side_effect=[[reference], [second_level]])
    provider.get_citations = AsyncMock(side_effect=[[], []])

    result = await CitationDiscovery(provider).discover(
        [seed],
        ResearchConfig(max_depth=2, max_papers=10, top_k_expansion=5),
    )

    assert [(item.paper.paper_id, item.depth) for item in result.papers] == [
        ("seed", 0),
        ("reference", 1),
        ("second-level", 2),
    ]
    assert {(edge.source_paper_id, edge.target_paper_id) for edge in result.citations} == {
        ("seed", "reference"),
        ("reference", "second-level"),
    }
    assert provider.get_references.await_count == 2
    assert provider.get_citations.await_count == 2
