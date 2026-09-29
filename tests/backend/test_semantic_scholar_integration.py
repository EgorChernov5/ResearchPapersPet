import os
from uuid import uuid4

import pytest
from app.config import Settings
from app.domain.paper import ProviderPaper
from app.domain.project import ResearchConfig, ResearchQuestion
from app.providers.semantic_scholar import SemanticScholarProvider
from app.research.discovery import CitationDiscovery
from app.research.structures import DiscoverySelection


class ExternalCandidateSelector:
    """
    Ограничивает live neighborhood без подмены provider или traversal.

    Fallbacks:
        Кандидаты выбираются в стабильном provider-ID порядке.
    """

    def select(self, candidates, seeds, questions, limit) -> DiscoverySelection:
        """Возвращает bounded deterministic frontier для external smoke test."""

        selected = sorted(candidates, key=lambda paper: paper.paper_id)[:limit]
        return DiscoverySelection(
            papers=selected,
            preliminary_scores={paper.paper_id: 1.0 for paper in selected},
        )


@pytest.mark.external
@pytest.mark.skipif(
    os.getenv("RUN_EXTERNAL_RESEARCH_TESTS") != "1",
    reason="Set RUN_EXTERNAL_RESEARCH_TESTS=1 to call the live API",
)
@pytest.mark.asyncio
async def test_live_semantic_scholar_discovery_gets_bounded_neighborhood() -> None:
    """
    Проверяет настоящий CitationDiscovery через Semantic Scholar Graph API.

    Returns:
        None: Assertions подтверждают live neighborhood, hard limit и induced edges.

    Fallbacks:
        По умолчанию тест пропускается, чтобы обычный suite не зависел от сети и rate limits.
    """

    # Use a supported stable DOI identifier directly to avoid an unrelated metadata request.
    seed = ProviderPaper(
        paper_id="DOI:10.18653/v1/N18-1074",
        title="FEVER: a Large-scale Dataset for Fact Extraction and VERification",
        external_ids={"doi": "10.18653/v1/N18-1074"},
        year=2018,
    )
    provider = SemanticScholarProvider(Settings())
    try:
        result = await CitationDiscovery(provider, ExternalCandidateSelector()).discover(
            [seed],
            [ResearchQuestion(project_id=uuid4(), text="Fact verification")],
            ResearchConfig(max_depth=1, max_papers=3, top_k_expansion=2),
        )
    finally:
        await provider.close()

    assert result.papers[0].is_seed is True
    assert len(result.papers) > 1
    assert len(result.papers) <= 3
    selected_ids = {item.paper.paper_id for item in result.papers}
    assert all(
        edge.source_paper_id in selected_ids and edge.target_paper_id in selected_ids
        for edge in result.citations
    )
