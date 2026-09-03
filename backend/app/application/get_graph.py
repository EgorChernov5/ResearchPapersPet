from uuid import UUID

from sqlalchemy.orm import sessionmaker

from app.application.exceptions import ResourceNotFoundError
from app.domain.graph import ProjectGraph
from app.repositories.citations import CitationRepository
from app.repositories.papers import ProjectPaperRepository
from app.repositories.projects import ProjectRepository


class GetResearchGraph:
    """
    Возвращает persisted citation subgraph после read-time filters.

    Attributes:
        session_factory (sessionmaker): Фабрика SQLAlchemy sessions.

    Fallbacks:
        Edges автоматически ограничиваются обеими отфильтрованными node sides.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        """
        Создаёт graph read use case.

        Parameters:
            session_factory (sessionmaker): Фабрика transaction sessions.

        Returns:
            None: Метод сохраняет dependency.

        Fallbacks:
            Session закрывается после materialization graph DTO.
        """

        self.session_factory = session_factory

    def execute(
        self,
        project_id: UUID,
        min_topic_score: float | None = None,
        min_final_score: float | None = None,
        min_year: int | None = None,
        min_citations: int | None = None,
        max_depth: int | None = None,
        category: str | None = None,
        is_seed: bool | None = None,
    ) -> ProjectGraph:
        """
        Загружает filtered nodes и internal citation edges.

        Parameters:
            project_id (UUID): Идентификатор проекта.
            min_topic_score (float | None): Минимальный topic score.
            min_final_score (float | None): Минимальный final score.
            min_year (int | None): Минимальный publication year.
            min_citations (int | None): Минимальный citation count.
            max_depth (int | None): Максимальная discovery depth.
            category (str | None): Требуемая category.
            is_seed (bool | None): Seed/discovered filter.

        Returns:
            ProjectGraph: Nodes и edges готовые для API serialization.

        Fallbacks:
            Missing project даёт ResourceNotFoundError; empty result валиден.
        """

        # Validate graph filters without invoking research or provider dependencies.
        scores = (min_topic_score, min_final_score)
        if any(score is not None and not 0 <= score <= 1 for score in scores):
            raise ValueError("Score filters must be between 0 and 1")
        if min_year is not None and min_year < 1000:
            raise ValueError("min_year must be at least 1000")
        if min_citations is not None and min_citations < 0:
            raise ValueError("min_citations must be non-negative")
        if max_depth is not None and max_depth < 0:
            raise ValueError("max_depth must be non-negative")

        with self.session_factory() as session:
            if ProjectRepository(session).get_config(project_id) is None:
                raise ResourceNotFoundError(f"Research project {project_id} was not found")
            papers = ProjectPaperRepository(session).get_ranked(
                project_id=project_id,
                min_topic_score=min_topic_score,
                min_final_score=min_final_score,
                min_year=min_year,
                min_citations=min_citations,
                max_depth=max_depth,
                category=category,
                is_seed=is_seed,
            )
            paper_ids = {paper.paper_id for paper in papers}
            citations = CitationRepository(session).get_for_papers(paper_ids)
            return ProjectGraph(papers=papers, citations=citations)
