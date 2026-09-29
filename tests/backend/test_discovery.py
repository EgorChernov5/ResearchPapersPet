from uuid import uuid4

import pytest
from app.domain.paper import ProviderPaper
from app.domain.project import ResearchConfig, ResearchQuestion
from app.providers.base import (
    ScholarlyPaperNotFoundError,
    ScholarlyProvider,
    ScholarlyProviderError,
)
from app.research.discovery import CitationDiscovery
from app.research.structures import DiscoverySelection


class FixtureScholarlyProvider(ScholarlyProvider):
    """
    Возвращает записанный citation graph и фиксирует реальные contract calls.

    Attributes:
        references (dict): Reference adjacency по provider ID.
        citations (dict): Citation adjacency по provider ID.
        failures (set): Направления, которые завершаются provider error.

    Fallbacks:
        Отсутствующий adjacency возвращает пустой neighborhood.
    """

    def __init__(self, references=None, citations=None, failures=None) -> None:
        """Создаёт deterministic provider fixture."""

        self.references = references or {}
        self.citations = citations or {}
        self.failures = failures or set()
        self.reference_calls = []
        self.citation_calls = []

    async def get_paper(self, identifier: str) -> ProviderPaper:
        """Возвращает paper из записанного графа или not-found."""

        for paper in self._papers():
            if paper.paper_id == identifier:
                return paper
        raise ScholarlyPaperNotFoundError(identifier)

    async def get_papers_batch(self, identifiers: list[str]) -> list[ProviderPaper]:
        """Возвращает найденные papers в порядке identifiers."""

        papers = {paper.paper_id: paper for paper in self._papers()}
        return [papers[identifier] for identifier in identifiers if identifier in papers]

    async def search_papers(
        self,
        query: str,
        limit: int = 10,
        year: int | None = None,
    ) -> list[ProviderPaper]:
        """Возвращает title matches из записанного графа."""

        return [
            paper
            for paper in self._papers()
            if query.casefold() in paper.title.casefold() and (year is None or paper.year == year)
        ][:limit]

    async def get_references(self, paper_id: str, limit: int = 1000) -> list[ProviderPaper]:
        """Возвращает и записывает reference request."""

        self.reference_calls.append((paper_id, limit))
        if (paper_id, "references") in self.failures:
            raise ScholarlyProviderError(f"references failed for {paper_id}")
        return self.references.get(paper_id, [])[:limit]

    async def get_citations(self, paper_id: str, limit: int = 1000) -> list[ProviderPaper]:
        """Возвращает и записывает citation request."""

        self.citation_calls.append((paper_id, limit))
        if (paper_id, "citations") in self.failures:
            raise ScholarlyProviderError(f"citations failed for {paper_id}")
        return self.citations.get(paper_id, [])[:limit]

    def _papers(self) -> list[ProviderPaper]:
        """Собирает уникальные papers из adjacency lists."""

        papers = {}
        for adjacency in (self.references, self.citations):
            for neighbors in adjacency.values():
                for paper in neighbors:
                    papers[paper.paper_id] = paper
        return list(papers.values())


class FixtureCandidateSelector:
    """
    Реализует selection contract с детерминированными scores.

    Attributes:
        scores (dict[str, float | None]): Score по provider paper ID.
        calls (list[list[str]]): Candidate pools, переданные после дедупликации.

    Fallbacks:
        Неизвестная paper получает score 1.0.
    """

    def __init__(self, scores=None) -> None:
        """Создаёт deterministic selector fixture."""

        self.scores = scores or {}
        self.calls = []

    def select(self, candidates, seeds, questions, limit) -> DiscoverySelection:
        """Выбирает лучшие уникальные candidates в стабильном порядке."""

        self.calls.append([paper.paper_id for paper in candidates])
        ranked = sorted(
            candidates,
            key=lambda paper: (-self.scores.get(paper.paper_id, 1.0), paper.paper_id),
        )[:limit]
        return DiscoverySelection(
            papers=ranked,
            preliminary_scores={
                paper.paper_id: self.scores.get(paper.paper_id, 1.0) for paper in ranked
            },
        )


@pytest.mark.parametrize("max_depth", [1, 2, 3, 5])
@pytest.mark.asyncio
async def test_discovery_traverses_each_depth(max_depth: int) -> None:
    """Проверяет bounded BFS для глубин 1, 2, 3 и 5."""

    papers = [ProviderPaper(f"p-{index}", f"Paper {index}", {}) for index in range(6)]
    provider = FixtureScholarlyProvider(
        references={papers[index].paper_id: [papers[index + 1]] for index in range(5)}
    )
    question = ResearchQuestion(uuid4(), "Which papers follow the seed?")

    result = await CitationDiscovery(provider, FixtureCandidateSelector()).discover(
        [papers[0]],
        [question],
        ResearchConfig(max_depth=max_depth, max_papers=20, top_k_expansion=5),
    )

    assert [(item.paper.paper_id, item.depth) for item in result.papers] == [
        (f"p-{index}", index) for index in range(max_depth + 1)
    ]
    assert [paper_id for paper_id, _ in provider.citation_calls] == [
        f"p-{index}" for index in range(max_depth)
    ]


@pytest.mark.asyncio
async def test_discovery_cycle_keeps_minimum_depth_without_duplicates() -> None:
    """Проверяет завершение цикла и минимальную достигнутую depth."""

    seed = ProviderPaper("seed", "Seed", {})
    first = ProviderPaper("first", "First", {})
    second = ProviderPaper("second", "Second", {})
    provider = FixtureScholarlyProvider(
        references={"seed": [first], "first": [second], "second": [seed]}
    )

    result = await CitationDiscovery(provider, FixtureCandidateSelector()).discover(
        [seed],
        [ResearchQuestion(uuid4(), "Cycle")],
        ResearchConfig(max_depth=5, max_papers=10, top_k_expansion=3),
    )

    assert [(item.paper.paper_id, item.depth) for item in result.papers] == [
        ("seed", 0),
        ("first", 1),
        ("second", 2),
    ]
    assert len({item.paper.paper_id for item in result.papers}) == 3
    assert {("seed", "first"), ("first", "second"), ("second", "seed")} == {
        (edge.source_paper_id, edge.target_paper_id) for edge in result.citations
    }


@pytest.mark.asyncio
async def test_discovery_applies_global_level_and_project_limits() -> None:
    """Проверяет top_k на уровень и max_papers с учётом seed."""

    seed = ProviderPaper("seed", "Seed", {})
    first_level = [ProviderPaper(f"first-{index}", f"First {index}", {}) for index in range(4)]
    second_level = [ProviderPaper(f"second-{index}", f"Second {index}", {}) for index in range(4)]
    provider = FixtureScholarlyProvider(
        references={
            "seed": first_level,
            "first-0": second_level[:2],
            "first-1": second_level[2:],
        }
    )

    result = await CitationDiscovery(provider, FixtureCandidateSelector()).discover(
        [seed],
        [ResearchQuestion(uuid4(), "Limits")],
        ResearchConfig(max_depth=5, max_papers=4, top_k_expansion=2),
    )

    assert [item.depth for item in result.papers] == [0, 1, 1, 2]
    assert len(result.papers) == 4
    assert {paper_id for paper_id, _ in provider.citation_calls} >= {"first-0", "first-1"}


@pytest.mark.asyncio
async def test_discovery_expands_references_only_for_seed_and_relevant_papers() -> None:
    """Проверяет threshold references и citations для всего frontier."""

    seed = ProviderPaper("seed", "Seed", {})
    relevant = ProviderPaper("relevant", "Relevant", {})
    irrelevant = ProviderPaper("irrelevant", "Irrelevant", {})
    provider = FixtureScholarlyProvider(references={"seed": [relevant, irrelevant]})
    selector = FixtureCandidateSelector({"relevant": 0.9, "irrelevant": 0.2})

    await CitationDiscovery(provider, selector).discover(
        [seed],
        [ResearchQuestion(uuid4(), "Threshold")],
        ResearchConfig(
            max_depth=2,
            max_papers=10,
            top_k_expansion=2,
            expand_references_topic_threshold=0.75,
        ),
    )

    assert [paper_id for paper_id, _ in provider.reference_calls] == ["seed", "relevant"]
    assert [paper_id for paper_id, _ in provider.citation_calls] == [
        "seed",
        "relevant",
        "irrelevant",
    ]


@pytest.mark.asyncio
async def test_discovery_deduplicates_before_selection_and_isolates_failure() -> None:
    """Проверяет pre-scoring deduplication и сохранение успешной ветви."""

    first_seed = ProviderPaper("seed-1", "Seed One", {})
    second_seed = ProviderPaper("seed-2", "Seed Two", {})
    shared = ProviderPaper("shared", "Shared", {})
    provider = FixtureScholarlyProvider(
        references={"seed-1": [shared], "seed-2": [shared]},
        failures={("seed-1", "citations")},
    )
    selector = FixtureCandidateSelector()

    result = await CitationDiscovery(provider, selector).discover(
        [first_seed, second_seed],
        [ResearchQuestion(uuid4(), "Failure isolation")],
        ResearchConfig(max_depth=2, max_papers=10, top_k_expansion=3),
    )

    assert selector.calls[0] == ["shared"]
    assert [item.paper.paper_id for item in result.papers] == ["seed-1", "seed-2", "shared"]
    assert [(failure.paper_id, failure.direction) for failure in result.failures] == [
        ("seed-1", "citations")
    ]


@pytest.mark.asyncio
async def test_discovery_stops_on_empty_frontier() -> None:
    """Проверяет раннюю остановку без лишних provider calls."""

    seed = ProviderPaper("seed", "Seed", {})
    provider = FixtureScholarlyProvider()

    result = await CitationDiscovery(provider, FixtureCandidateSelector()).discover(
        [seed],
        [ResearchQuestion(uuid4(), "Empty")],
        ResearchConfig(max_depth=5, max_papers=10, top_k_expansion=3),
    )

    assert [item.paper.paper_id for item in result.papers] == ["seed"]
    assert provider.reference_calls == [("seed", 10)]
    assert provider.citation_calls == [("seed", 10)]
