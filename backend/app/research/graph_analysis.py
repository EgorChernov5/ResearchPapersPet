from uuid import UUID

import networkx as nx

from app.domain.citation import Citation
from app.domain.scoring import PaperGraphMetrics


class GraphAnalyzer:
    """
    Строит directed project subgraph и рассчитывает structural metrics.

    Fallbacks:
        Disconnected nodes сохраняются с missing distance, но с валидными degree и PageRank.
    """

    def analyze(
        self,
        paper_ids: set[UUID],
        citations: list[Citation],
        seed_paper_ids: set[UUID],
    ) -> list[PaperGraphMetrics]:
        """
        Рассчитывает graph metrics для каждой статьи проекта.

        Parameters:
            paper_ids (set[UUID]): Узлы project subgraph.
            citations (list[Citation]): Global edges, ограниченные project papers.
            seed_paper_ids (set[UUID]): Seed nodes проекта.

        Returns:
            list[PaperGraphMetrics]: Метрики в стабильном paper ID порядке.

        Fallbacks:
            Пустой набор papers возвращает пустой список.
        """

        if not paper_ids:
            return []

        # Build the complete directed graph, including isolated project papers.
        graph = nx.DiGraph()
        graph.add_nodes_from(paper_ids)
        graph.add_edges_from(
            (citation.source_paper_id, citation.target_paper_id)
            for citation in citations
            if citation.source_paper_id in paper_ids
            and citation.target_paper_id in paper_ids
            and citation.source_paper_id != citation.target_paper_id
        )

        # Normalize PageRank by the strongest node for a stable zero-to-one project score.
        raw_pagerank = nx.pagerank(graph)
        max_pagerank = max(raw_pagerank.values(), default=0.0)
        pagerank_scores = {
            paper_id: value / max_pagerank if max_pagerank > 0 else 0.0
            for paper_id, value in raw_pagerank.items()
        }

        # Use undirected paths so both references and citing papers remain reachable from seeds.
        undirected_graph = graph.to_undirected()
        valid_seeds = seed_paper_ids & paper_ids
        distances = (
            nx.multi_source_dijkstra_path_length(undirected_graph, valid_seeds)
            if valid_seeds
            else {}
        )
        degree_centrality = nx.degree_centrality(undirected_graph)
        denominator = 2 * (len(paper_ids) - 1)

        # Preserve raw degrees while deriving bounded proximity and connectivity scores.
        metrics = []
        for paper_id in sorted(paper_ids, key=str):
            distance = distances.get(paper_id)
            in_degree = graph.in_degree(paper_id)
            out_degree = graph.out_degree(paper_id)
            metrics.append(
                PaperGraphMetrics(
                    paper_id=paper_id,
                    in_degree=in_degree,
                    out_degree=out_degree,
                    degree_centrality=degree_centrality.get(paper_id, 0.0),
                    distance_from_seed=distance,
                    distance_score=1.0 / (distance + 1) if distance is not None else None,
                    connectivity_score=(in_degree + out_degree) / denominator
                    if denominator > 0
                    else 0.0,
                    pagerank_score=pagerank_scores.get(paper_id, 0.0),
                )
            )
        return metrics
