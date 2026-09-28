import os

import pytest
from app.config import Settings
from app.providers.semantic_scholar import SemanticScholarProvider


@pytest.mark.external
@pytest.mark.skipif(
    os.getenv("RUN_EXTERNAL_RESEARCH_TESTS") != "1",
    reason="Set RUN_EXTERNAL_RESEARCH_TESTS=1 to call the live API",
)
@pytest.mark.asyncio
async def test_live_semantic_scholar_resolves_known_paper() -> None:
    """
    Проверяет контракт адаптера с реальным Semantic Scholar Graph API.

    Returns:
        None: Assertions подтверждают canonical metadata известной статьи.

    Fallbacks:
        По умолчанию тест пропускается, чтобы обычный suite не зависел от сети и rate limits.
    """

    # Resolve the stable ACL Anthology DOI through the real external service.
    provider = SemanticScholarProvider(Settings())
    try:
        paper = await provider.get_paper("DOI:10.18653/v1/N18-1074")
    finally:
        await provider.close()

    assert paper.paper_id
    assert paper.title.startswith("FEVER:")
    assert paper.year == 2018
    assert paper.external_ids.get("doi", "").lower() == "10.18653/v1/n18-1074"
