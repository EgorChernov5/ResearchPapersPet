from app.domain.paper import ProviderPaper
from app.research.deduplication import PaperDeduplicator


def test_deduplicate_by_doi_and_merge_missing_metadata() -> None:
    """
    Проверяет DOI fallback и объединение неполных provider metadata.

    Returns:
        None: Assertions подтверждают один enriched canonical record.

    Fallbacks:
        Test failure показывает duplicate global Paper risk.
    """

    papers = [
        ProviderPaper(
            paper_id="s2-first",
            title="Canonical Paper",
            year=2024,
            external_ids={"doi": "10.1000/example"},
        ),
        ProviderPaper(
            paper_id="s2-second",
            title="Canonical Paper Extended",
            abstract="Complete abstract",
            year=2024,
            citation_count=42,
            external_ids={"doi": "10.1000/example", "arxiv": "2401.00001"},
        ),
    ]

    result = PaperDeduplicator().deduplicate(papers)

    assert len(result) == 1
    assert result[0].paper_id == "s2-first"
    assert result[0].abstract == "Complete abstract"
    assert result[0].citation_count == 42
    assert result[0].external_ids["arxiv"] == "2401.00001"


def test_deduplicate_by_normalized_title_as_last_fallback() -> None:
    """
    Проверяет normalized title fallback при отсутствии external identifiers.

    Returns:
        None: Assertions подтверждают stable deduplication.

    Fallbacks:
        Пунктуация и регистр не создают duplicate paper.
    """

    papers = [
        ProviderPaper("first", "Graph-Aware RAG!", {}, year=2024),
        ProviderPaper("second", "graph aware rag", {}, year=2024),
    ]

    assert len(PaperDeduplicator().deduplicate(papers)) == 1
