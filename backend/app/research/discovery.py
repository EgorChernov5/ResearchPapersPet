from app.domain.paper import ProviderPaper
from app.domain.project import ResearchConfig, ResearchQuestion
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
    Строит bounded breadth-first citation neighborhood до max_depth.

    Attributes:
        provider (ScholarlyProvider): Источник references и citations.
        candidate_selector (object): Preliminary scorer и balanced selector уровня.
        deduplicator (PaperDeduplicator): Canonical paper deduplication.

    Fallbacks:
        Ошибка одного direction request не останавливает остальные ветви обхода.
    """

    def __init__(
        self,
        provider: ScholarlyProvider,
        candidate_selector: object,
        deduplicator: PaperDeduplicator | None = None,
    ) -> None:
        """
        Создаёт многоуровневый citation discovery service.

        Parameters:
            provider (ScholarlyProvider): Scientific provider adapter.
            candidate_selector (object): Компонент semantic selection одного уровня.
            deduplicator (PaperDeduplicator | None): Deduplicator. По умолчанию: None.

        Returns:
            None: Метод инициализирует service.

        Fallbacks:
            Без injected deduplicator создаётся стандартная реализация.
        """

        self.provider = provider
        self.candidate_selector = candidate_selector
        self.deduplicator = deduplicator or PaperDeduplicator()

    async def discover(
        self,
        seeds: list[ProviderPaper],
        questions: list[ResearchQuestion],
        config: ResearchConfig,
    ) -> CitationDiscoveryResult:
        """
        Обходит citation graph по уровням с semantic selection каждого frontier.

        Parameters:
            seeds (list[ProviderPaper]): Разрешённые seed metadata.
            questions (list[ResearchQuestion]): Research questions проекта.
            config (ResearchConfig): Depth, paper, level и relevance limits.

        Returns:
            CitationDiscoveryResult: Selected papers, induced edges и failures.

        Fallbacks:
            Пустой seed list возвращает пустой result без provider calls.
        """

        result = CitationDiscoveryResult()
        unique_seeds = self.deduplicator.deduplicate(seeds)
        selected_seeds = unique_seeds[: config.max_papers]
        selected_by_id = {paper.paper_id: paper for paper in selected_seeds}
        depth_by_id = {paper.paper_id: 0 for paper in selected_seeds}
        preliminary_scores = {}
        frontier = selected_seeds
        candidate_edges = []

        # Record seeds first so max_papers includes them with deterministic truncation.
        for omitted_seed in unique_seeds[config.max_papers :]:
            result.failures.append(
                DiscoveryFailure(
                    paper_id=omitted_seed.paper_id,
                    direction="seed_limit",
                    reason="Seed omitted because max_papers was reached",
                )
            )

        # Expand one complete frontier at a time until a hard bound terminates traversal.
        for depth in range(config.max_depth):
            if not frontier or len(selected_by_id) >= config.max_papers:
                break
            candidates = []
            for paper in frontier:
                if depth == 0 or (
                    preliminary_scores.get(paper.paper_id) is not None
                    and preliminary_scores[paper.paper_id]
                    >= config.expand_references_topic_threshold
                ):
                    try:
                        references = await self.provider.get_references(
                            paper.paper_id,
                            limit=config.max_papers,
                        )
                        for reference in references:
                            candidates.append(reference)
                            candidate_edges.append(
                                DiscoveredCitation(
                                    source_paper_id=paper.paper_id,
                                    target_paper_id=reference.paper_id,
                                )
                            )
                    except ScholarlyProviderError as error:
                        result.failures.append(
                            DiscoveryFailure(paper.paper_id, "references", str(error))
                        )

                # Citations are requested for every paper in the current frontier.
                try:
                    citations = await self.provider.get_citations(
                        paper.paper_id,
                        limit=config.max_papers,
                    )
                    for citation in citations:
                        candidates.append(citation)
                        candidate_edges.append(
                            DiscoveredCitation(
                                source_paper_id=citation.paper_id,
                                target_paper_id=paper.paper_id,
                            )
                        )
                except ScholarlyProviderError as error:
                    result.failures.append(
                        DiscoveryFailure(paper.paper_id, "citations", str(error))
                    )

            # Deduplicate before embedding and never score already selected papers again.
            candidates = [
                paper
                for paper in candidates
                if (config.min_year is None or paper.year is None or paper.year >= config.min_year)
            ]
            candidates = self.deduplicator.deduplicate(candidates)
            candidates = [paper for paper in candidates if paper.paper_id not in selected_by_id]
            available_slots = min(
                config.top_k_expansion,
                config.max_papers - len(selected_by_id),
            )
            if not candidates or available_slots < 1:
                frontier = []
                continue
            selection = self.candidate_selector.select(
                candidates,
                selected_seeds,
                questions,
                available_slots,
            )
            frontier = selection.papers[:available_slots]
            for paper in frontier:
                selected_by_id[paper.paper_id] = paper
                depth_by_id[paper.paper_id] = depth + 1
                preliminary_scores[paper.paper_id] = selection.preliminary_scores.get(
                    paper.paper_id
                )

        # Persist only selected papers and the induced unique non-self citation graph.
        result.papers = [
            DiscoveredPaper(
                paper=paper,
                is_seed=depth_by_id[paper.paper_id] == 0,
                depth=depth_by_id[paper.paper_id],
            )
            for paper in selected_by_id.values()
        ]
        selected_ids = set(selected_by_id)
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
