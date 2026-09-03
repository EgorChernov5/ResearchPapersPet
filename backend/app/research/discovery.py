from app.domain.paper import ProviderPaper
from app.domain.project import ResearchConfig
from app.providers.base import ScholarlyProvider, ScholarlyProviderError
from app.research.deduplication import PaperDeduplicator
from app.research.structures import (
    CitationDiscoveryResult,
    DiscoveredCitation,
    DiscoveredPaper,
    DiscoveryFailure,
)


class CitationDiscovery:
    """
    Строит bounded citation neighborhood depth=1 для seed papers.

    Attributes:
        provider (ScholarlyProvider): Источник references и citations.
        deduplicator (PaperDeduplicator): Canonical paper deduplication.

    Fallbacks:
        Ошибка одного direction request не останавливает остальные requests.
    """

    def __init__(
        self,
        provider: ScholarlyProvider,
        deduplicator: PaperDeduplicator | None = None,
    ) -> None:
        """
        Создаёт depth=1 citation discovery service.

        Parameters:
            provider (ScholarlyProvider): Scientific provider adapter.
            deduplicator (PaperDeduplicator | None): Deduplicator. По умолчанию: None.

        Returns:
            None: Метод инициализирует service.

        Fallbacks:
            Без injected deduplicator создаётся стандартная реализация.
        """

        self.provider = provider
        self.deduplicator = deduplicator or PaperDeduplicator()

    async def discover(
        self,
        seeds: list[ProviderPaper],
        config: ResearchConfig,
    ) -> CitationDiscoveryResult:
        """
        Получает references и citations seeds с depth=1 и hard limits.

        Parameters:
            seeds (list[ProviderPaper]): Разрешённые seed metadata.
            config (ResearchConfig): MAX_PAPERS, TOP_K и year filter.

        Returns:
            CitationDiscoveryResult: Selected papers, edges и failures.

        Fallbacks:
            Пустой seed list возвращает пустой result без provider calls.
        """

        result = CitationDiscoveryResult()
        unique_seeds = self.deduplicator.deduplicate(seeds)
        selected_seeds = unique_seeds[: config.max_papers]
        candidates = []
        candidate_edges = []

        # Record seeds first so max_papers always has deterministic semantics.
        result.papers.extend(
            DiscoveredPaper(paper=paper, is_seed=True, depth=0) for paper in selected_seeds
        )
        for omitted_seed in unique_seeds[config.max_papers :]:
            result.failures.append(
                DiscoveryFailure(
                    paper_id=omitted_seed.paper_id,
                    direction="seed_limit",
                    reason="Seed omitted because max_papers was reached",
                )
            )

        # Seeds expand in both directions; each request is bounded by TOP_K_EXPANSION.
        for seed in selected_seeds:
            try:
                references = await self.provider.get_references(
                    seed.paper_id,
                    limit=config.top_k_expansion,
                )
                for paper in references:
                    candidates.append(paper)
                    candidate_edges.append(
                        DiscoveredCitation(
                            source_paper_id=seed.paper_id,
                            target_paper_id=paper.paper_id,
                        )
                    )
            except ScholarlyProviderError as error:
                result.failures.append(
                    DiscoveryFailure(
                        paper_id=seed.paper_id,
                        direction="references",
                        reason=str(error),
                    )
                )
            try:
                citations = await self.provider.get_citations(
                    seed.paper_id,
                    limit=config.top_k_expansion,
                )
                for paper in citations:
                    candidates.append(paper)
                    candidate_edges.append(
                        DiscoveredCitation(
                            source_paper_id=paper.paper_id,
                            target_paper_id=seed.paper_id,
                        )
                    )
            except ScholarlyProviderError as error:
                result.failures.append(
                    DiscoveryFailure(
                        paper_id=seed.paper_id,
                        direction="citations",
                        reason=str(error),
                    )
                )

        # Filter known old years without treating a missing year as zero relevance.
        candidates = [
            paper
            for paper in candidates
            if config.min_year is None or paper.year is None or paper.year >= config.min_year
        ]
        candidates = self.deduplicator.deduplicate(candidates)
        seed_ids = {paper.paper_id for paper in selected_seeds}
        candidates = [paper for paper in candidates if paper.paper_id not in seed_ids]

        # Until semantic scoring exists, use stable metadata-only ordering before truncation.
        candidates.sort(
            key=lambda paper: (
                -(paper.citation_count if paper.citation_count is not None else -1),
                -(paper.year if paper.year is not None else -1),
                paper.paper_id,
            )
        )
        available_slots = max(config.max_papers - len(selected_seeds), 0)
        selected_candidates = candidates[:available_slots]
        selected_ids = seed_ids.union(paper.paper_id for paper in selected_candidates)
        result.papers.extend(
            DiscoveredPaper(paper=paper, is_seed=False, depth=1) for paper in selected_candidates
        )

        # Keep only unique non-self edges whose endpoints survived hard limits.
        result.citations = list(
            dict.fromkeys(
                edge
                for edge in candidate_edges
                if edge.source_paper_id in selected_ids
                and edge.target_paper_id in selected_ids
                and edge.source_paper_id != edge.target_paper_id
            )
        )
        return result
