from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import PAPER_RANKING_SORT_FIELDS, SUPPORTED_EXTERNAL_IDENTIFIER_PROVIDERS
from app.domain.paper import Paper, ProviderPaper
from app.domain.scoring import PaperFinalScore, ProjectPaper, RankedPaper
from app.infrastructure.models import (
    ExternalIdentifierModel,
    PaperModel,
    ProjectPaperModel,
)


class PaperRepository:
    """
    Сохраняет и обновляет глобальные scientific papers.

    Attributes:
        session (Session): Текущая SQLAlchemy transaction session.

    Fallbacks:
        Duplicate metadata разрешаются до INSERT по canonical identifiers.
    """

    def __init__(self, session: Session) -> None:
        """
        Создаёт repository внутри существующей transaction boundary.

        Parameters:
            session (Session): SQLAlchemy session.

        Returns:
            None: Метод сохраняет session.

        Fallbacks:
            Commit и rollback остаются ответственностью application layer.
        """

        self.session = session

    def upsert(self, paper: ProviderPaper) -> Paper:
        """
        Создаёт или обогащает глобальную Paper без project duplication.

        Parameters:
            paper (ProviderPaper): Нормализованные provider metadata.

        Returns:
            Paper: Актуальная доменная global paper.

        Fallbacks:
            Missing metadata не затирают уже сохранённые значения.
        """

        # Resolve an existing row by S2 first, then by supported external identifiers.
        model = self.session.scalar(
            select(PaperModel).where(PaperModel.semantic_scholar_id == paper.paper_id)
        )
        normalized_ids = {
            key.casefold(): str(value)
            for key, value in paper.external_ids.items()
            if value and key.casefold() in SUPPORTED_EXTERNAL_IDENTIFIER_PROVIDERS
        }
        normalized_ids.setdefault("semantic_scholar", paper.paper_id)
        if model is None:
            for provider in ("doi", "arxiv", "acl"):
                value = normalized_ids.get(provider)
                if value is None:
                    continue
                model = self.session.scalar(
                    select(PaperModel)
                    .join(
                        ExternalIdentifierModel,
                        ExternalIdentifierModel.paper_id == PaperModel.id,
                    )
                    .where(
                        ExternalIdentifierModel.provider == provider,
                        ExternalIdentifierModel.value == value,
                    )
                )
                if model is not None:
                    break

        # Create the global row once or enrich its non-missing fields.
        if model is None:
            model = PaperModel(
                semantic_scholar_id=paper.paper_id,
                title=paper.title,
                abstract=paper.abstract,
                year=paper.year,
                citation_count=paper.citation_count,
                influential_citation_count=paper.influential_citation_count,
                reference_count=paper.reference_count,
                authors=list(paper.authors),
                categories=list(paper.categories),
                pdf_url=paper.pdf_url,
            )
            self.session.add(model)
            self.session.flush()
        else:
            if model.semantic_scholar_id is None:
                model.semantic_scholar_id = paper.paper_id
            model.title = paper.title or model.title
            for attribute in (
                "abstract",
                "year",
                "citation_count",
                "influential_citation_count",
                "reference_count",
                "pdf_url",
            ):
                value = getattr(paper, attribute)
                if value is not None:
                    setattr(model, attribute, value)
            if paper.authors:
                model.authors = list(paper.authors)
            if paper.categories:
                model.categories = list(paper.categories)

        # Add only missing identifier providers for the retained global row.
        existing_identifiers = {
            item.provider: item.value
            for item in self.session.scalars(
                select(ExternalIdentifierModel).where(ExternalIdentifierModel.paper_id == model.id)
            )
        }
        for provider, value in normalized_ids.items():
            identifier_owner = self.session.scalar(
                select(ExternalIdentifierModel).where(
                    ExternalIdentifierModel.provider == provider,
                    ExternalIdentifierModel.value == value,
                )
            )
            if provider not in existing_identifiers and identifier_owner is None:
                self.session.add(
                    ExternalIdentifierModel(
                        paper_id=model.id,
                        provider=provider,
                        value=value,
                    )
                )
        self.session.flush()
        return Paper(
            id=model.id,
            semantic_scholar_id=model.semantic_scholar_id,
            title=model.title,
            abstract=model.abstract,
            year=model.year,
            citation_count=model.citation_count,
            influential_citation_count=model.influential_citation_count,
            reference_count=model.reference_count,
            authors=list(model.authors),
            categories=list(model.categories),
            pdf_url=model.pdf_url,
        )

    def get_external_identifier(self, paper_id: UUID, provider: str) -> str | None:
        """
        Возвращает canonical external identifier статьи.

        Parameters:
            paper_id (UUID): Идентификатор global Paper.
            provider (str): Нормализованное имя provider.

        Returns:
            str | None: Сохранённое значение или None.

        Fallbacks:
            Missing paper/provider не создаёт synthetic identifier.
        """

        # Read only the requested provider to keep automatic source selection explicit.
        return self.session.scalar(
            select(ExternalIdentifierModel.value).where(
                ExternalIdentifierModel.paper_id == paper_id,
                ExternalIdentifierModel.provider == provider.casefold(),
            )
        )


class ProjectPaperRepository:
    """
    Сохраняет project-specific membership и discovery depth.

    Attributes:
        session (Session): Текущая SQLAlchemy transaction session.

    Fallbacks:
        Повторное discovery сохраняет минимальный depth и seed status.
    """

    def __init__(self, session: Session) -> None:
        """
        Создаёт repository внутри существующей transaction boundary.

        Parameters:
            session (Session): SQLAlchemy session.

        Returns:
            None: Метод сохраняет session.

        Fallbacks:
            Commit и rollback выполняет application layer.
        """

        self.session = session

    def upsert(
        self,
        project_id: UUID,
        paper_id: UUID,
        is_seed: bool,
        depth: int,
    ) -> ProjectPaper:
        """
        Создаёт или обновляет project-paper association.

        Parameters:
            project_id (UUID): Идентификатор проекта.
            paper_id (UUID): Идентификатор global Paper.
            is_seed (bool): Признак seed paper.
            depth (int): Минимальная depth от seed.

        Returns:
            ProjectPaper: Актуальная project-specific domain entity.

        Fallbacks:
            Повторный проход не увеличивает ранее найденную depth.
        """

        model = self.session.scalar(
            select(ProjectPaperModel).where(
                ProjectPaperModel.project_id == project_id,
                ProjectPaperModel.paper_id == paper_id,
            )
        )
        if model is None:
            model = ProjectPaperModel(
                project_id=project_id,
                paper_id=paper_id,
                is_seed=is_seed,
                depth=depth,
            )
            self.session.add(model)
        else:
            model.is_seed = model.is_seed or is_seed
            model.depth = depth if model.depth is None else min(model.depth, depth)
        self.session.flush()
        return ProjectPaper(
            id=model.id,
            project_id=model.project_id,
            paper_id=model.paper_id,
            is_seed=model.is_seed,
            depth=model.depth,
            query_similarity=model.query_similarity,
            seed_similarity=model.seed_similarity,
            topic_score=model.topic_score,
            citation_score=model.citation_score,
            recency_score=model.recency_score,
            impact_score=model.impact_score,
            distance_score=model.distance_score,
            connectivity_score=model.connectivity_score,
            pagerank_score=model.pagerank_score,
            graph_score=model.graph_score,
            final_score=model.final_score,
        )

    def update_semantic_scores(
        self,
        project_id: UUID,
        paper_id: UUID,
        query_similarity: float | None,
        seed_similarity: float | None,
        topic_score: float | None,
    ) -> ProjectPaper:
        """
        Сохраняет aggregated semantic scores project paper.

        Parameters:
            project_id (UUID): Идентификатор проекта.
            paper_id (UUID): Идентификатор global Paper.
            query_similarity (float | None): Max question similarity.
            seed_similarity (float | None): Max seed similarity.
            topic_score (float | None): Max question topic score.

        Returns:
            ProjectPaper: Обновлённая project-specific entity.

        Fallbacks:
            Missing association вызывает ValueError вместо implicit INSERT.
        """

        model = self.session.scalar(
            select(ProjectPaperModel).where(
                ProjectPaperModel.project_id == project_id,
                ProjectPaperModel.paper_id == paper_id,
            )
        )
        if model is None:
            raise ValueError(f"Paper {paper_id} is not attached to project {project_id}")
        model.query_similarity = query_similarity
        model.seed_similarity = seed_similarity
        model.topic_score = topic_score
        self.session.flush()
        return ProjectPaper(
            id=model.id,
            project_id=model.project_id,
            paper_id=model.paper_id,
            is_seed=model.is_seed,
            depth=model.depth,
            query_similarity=model.query_similarity,
            seed_similarity=model.seed_similarity,
            topic_score=model.topic_score,
            citation_score=model.citation_score,
            recency_score=model.recency_score,
            impact_score=model.impact_score,
            distance_score=model.distance_score,
            connectivity_score=model.connectivity_score,
            pagerank_score=model.pagerank_score,
            graph_score=model.graph_score,
            final_score=model.final_score,
        )

    def get_many(self, project_id: UUID) -> list[ProjectPaper]:
        """
        Загружает project-specific discovery и scoring state.

        Parameters:
            project_id (UUID): Идентификатор проекта.

        Returns:
            list[ProjectPaper]: Associations в стабильном depth/paper порядке.

        Fallbacks:
            Проект без papers возвращает пустой список.
        """

        models = self.session.scalars(
            select(ProjectPaperModel)
            .where(ProjectPaperModel.project_id == project_id)
            .order_by(ProjectPaperModel.depth, ProjectPaperModel.paper_id)
        )
        return [
            ProjectPaper(
                id=model.id,
                project_id=model.project_id,
                paper_id=model.paper_id,
                is_seed=model.is_seed,
                depth=model.depth,
                query_similarity=model.query_similarity,
                seed_similarity=model.seed_similarity,
                topic_score=model.topic_score,
                citation_score=model.citation_score,
                recency_score=model.recency_score,
                impact_score=model.impact_score,
                distance_score=model.distance_score,
                connectivity_score=model.connectivity_score,
                pagerank_score=model.pagerank_score,
                graph_score=model.graph_score,
                final_score=model.final_score,
            )
            for model in models
        ]

    def get_ranked(
        self,
        project_id: UUID,
        min_topic_score: float | None = None,
        min_final_score: float | None = None,
        min_year: int | None = None,
        min_citations: int | None = None,
        max_depth: int | None = None,
        category: str | None = None,
        is_seed: bool | None = None,
        sort_by: str = "final_score",
        descending: bool = True,
    ) -> list[RankedPaper]:
        """
        Возвращает отфильтрованный и отсортированный project ranking.

        Parameters:
            project_id (UUID): Идентификатор проекта.
            min_topic_score (float | None): Минимальная semantic relevance.
            min_final_score (float | None): Минимальная итоговая relevance.
            min_year (int | None): Минимальный publication year.
            min_citations (int | None): Минимальный citation count.
            max_depth (int | None): Максимальная discovery depth.
            category (str | None): Требуемая paper category.
            is_seed (bool | None): Фильтр seed/discovered.
            sort_by (str): Разрешённое поле сортировки. По умолчанию: final_score.
            descending (bool): Направление сортировки. По умолчанию: True.

        Returns:
            list[RankedPaper]: Read models после filters и sorting.

        Fallbacks:
            Missing score не проходит соответствующий hard filter и сортируется последним.
        """

        if sort_by not in PAPER_RANKING_SORT_FIELDS:
            raise ValueError(f"Unsupported paper sort field: {sort_by}")

        # Load the bounded project result in one join; filtering never reruns research.
        rows = self.session.execute(
            select(PaperModel, ProjectPaperModel)
            .join(ProjectPaperModel, ProjectPaperModel.paper_id == PaperModel.id)
            .where(ProjectPaperModel.project_id == project_id)
        ).all()
        normalized_category = category.casefold() if category is not None else None
        ranked = []
        for paper, project_paper in rows:
            if min_topic_score is not None and (
                project_paper.topic_score is None or project_paper.topic_score < min_topic_score
            ):
                continue
            if min_final_score is not None and (
                project_paper.final_score is None or project_paper.final_score < min_final_score
            ):
                continue
            if min_year is not None and (paper.year is None or paper.year < min_year):
                continue
            if min_citations is not None and (
                paper.citation_count is None or paper.citation_count < min_citations
            ):
                continue
            if max_depth is not None and (
                project_paper.depth is None or project_paper.depth > max_depth
            ):
                continue
            if normalized_category is not None and normalized_category not in {
                item.casefold() for item in paper.categories
            }:
                continue
            if is_seed is not None and project_paper.is_seed != is_seed:
                continue
            ranked.append(
                RankedPaper(
                    paper_id=paper.id,
                    semantic_scholar_id=paper.semantic_scholar_id,
                    title=paper.title,
                    abstract=paper.abstract,
                    year=paper.year,
                    citation_count=paper.citation_count,
                    influential_citation_count=paper.influential_citation_count,
                    reference_count=paper.reference_count,
                    authors=list(paper.authors),
                    categories=list(paper.categories),
                    pdf_url=paper.pdf_url,
                    is_seed=project_paper.is_seed,
                    depth=project_paper.depth,
                    query_similarity=project_paper.query_similarity,
                    seed_similarity=project_paper.seed_similarity,
                    topic_score=project_paper.topic_score,
                    citation_score=project_paper.citation_score,
                    recency_score=project_paper.recency_score,
                    impact_score=project_paper.impact_score,
                    distance_score=project_paper.distance_score,
                    connectivity_score=project_paper.connectivity_score,
                    pagerank_score=project_paper.pagerank_score,
                    graph_score=project_paper.graph_score,
                    final_score=project_paper.final_score,
                )
            )

        # Keep missing sort values last for either sorting direction.
        available = [paper for paper in ranked if getattr(paper, sort_by) is not None]
        missing = [paper for paper in ranked if getattr(paper, sort_by) is None]
        available.sort(key=lambda paper: getattr(paper, sort_by), reverse=descending)
        return available + missing

    def get_ranked_paper(self, project_id: UUID, paper_id: UUID) -> RankedPaper | None:
        """
        Загружает одну paper view внутри проекта.

        Parameters:
            project_id (UUID): Идентификатор проекта.
            paper_id (UUID): Идентификатор глобальной статьи.

        Returns:
            RankedPaper | None: Project paper details или None.

        Fallbacks:
            Global paper вне проекта считается отсутствующей.
        """

        return next(
            (
                paper
                for paper in self.get_ranked(project_id, sort_by="title")
                if paper.paper_id == paper_id
            ),
            None,
        )

    def update_ranking_scores(
        self,
        project_id: UUID,
        score: PaperFinalScore,
    ) -> ProjectPaper:
        """
        Сохраняет graph, impact и final scores project paper.

        Parameters:
            project_id (UUID): Идентификатор проекта.
            score (PaperFinalScore): Полный ranking result статьи.

        Returns:
            ProjectPaper: Обновлённая project-specific entity.

        Fallbacks:
            Missing association вызывает ValueError вместо implicit INSERT.
        """

        model = self.session.scalar(
            select(ProjectPaperModel).where(
                ProjectPaperModel.project_id == project_id,
                ProjectPaperModel.paper_id == score.paper_id,
            )
        )
        if model is None:
            raise ValueError(f"Paper {score.paper_id} is not attached to project {project_id}")

        # Persist every Milestone 7 component atomically for one project paper.
        model.citation_score = score.citation_score
        model.recency_score = score.recency_score
        model.impact_score = score.impact_score
        model.distance_score = score.distance_score
        model.connectivity_score = score.connectivity_score
        model.pagerank_score = score.pagerank_score
        model.graph_score = score.graph_score
        model.final_score = score.final_score
        self.session.flush()
        return ProjectPaper(
            id=model.id,
            project_id=model.project_id,
            paper_id=model.paper_id,
            is_seed=model.is_seed,
            depth=model.depth,
            query_similarity=model.query_similarity,
            seed_similarity=model.seed_similarity,
            topic_score=model.topic_score,
            citation_score=model.citation_score,
            recency_score=model.recency_score,
            impact_score=model.impact_score,
            distance_score=model.distance_score,
            connectivity_score=model.connectivity_score,
            pagerank_score=model.pagerank_score,
            graph_score=model.graph_score,
            final_score=model.final_score,
        )
