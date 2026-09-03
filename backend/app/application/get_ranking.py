from uuid import UUID

from sqlalchemy.orm import sessionmaker

from app.application.exceptions import ResourceNotFoundError
from app.domain.scoring import PaperDetails, RankedPaper
from app.repositories.papers import ProjectPaperRepository
from app.repositories.projects import ProjectRepository
from app.repositories.semantic_scores import SemanticScoreRepository


class GetPaperRanking:
    """
    Возвращает persisted project ranking с read-time filters.

    Attributes:
        session_factory (sessionmaker): Фабрика SQLAlchemy sessions.

    Fallbacks:
        Filters не запускают provider requests, embeddings или worker pipeline.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        """
        Создаёт ranking use case.

        Parameters:
            session_factory (sessionmaker): Фабрика transaction sessions.

        Returns:
            None: Метод сохраняет dependency.

        Fallbacks:
            Read session закрывается после materialization.
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
        sort_by: str = "final_score",
        descending: bool = True,
    ) -> list[RankedPaper]:
        """
        Загружает ranking с hard filters и sorting.

        Parameters:
            project_id (UUID): Идентификатор проекта.
            min_topic_score (float | None): Минимальный topic score.
            min_final_score (float | None): Минимальный final score.
            min_year (int | None): Минимальный publication year.
            min_citations (int | None): Минимальный citation count.
            max_depth (int | None): Максимальная discovery depth.
            category (str | None): Требуемая category.
            is_seed (bool | None): Seed/discovered filter.
            sort_by (str): Поле sorting. По умолчанию: final_score.
            descending (bool): Descending sorting. По умолчанию: True.

        Returns:
            list[RankedPaper]: Filtered persisted results.

        Fallbacks:
            Missing project даёт ResourceNotFoundError.
        """

        # Validate query bounds before applying filters to persisted values.
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
            return ProjectPaperRepository(session).get_ranked(
                project_id=project_id,
                min_topic_score=min_topic_score,
                min_final_score=min_final_score,
                min_year=min_year,
                min_citations=min_citations,
                max_depth=max_depth,
                category=category,
                is_seed=is_seed,
                sort_by=sort_by,
                descending=descending,
            )


class GetPaperDetails:
    """
    Возвращает project paper metadata и per-question semantic scores.

    Attributes:
        session_factory (sessionmaker): Фабрика SQLAlchemy sessions.

    Fallbacks:
        Paper вне проекта считается отсутствующей.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        """
        Создаёт details use case.

        Parameters:
            session_factory (sessionmaker): Фабрика transaction sessions.

        Returns:
            None: Метод сохраняет dependency.

        Fallbacks:
            Read-only session закрывается после DTO construction.
        """

        self.session_factory = session_factory

    def execute(self, project_id: UUID, paper_id: UUID) -> PaperDetails:
        """
        Загружает paper details.

        Parameters:
            project_id (UUID): Идентификатор проекта.
            paper_id (UUID): Идентификатор global paper.

        Returns:
            PaperDetails: Project-level paper view.

        Fallbacks:
            Missing project paper даёт ResourceNotFoundError.
        """

        with self.session_factory() as session:
            paper = ProjectPaperRepository(session).get_ranked_paper(project_id, paper_id)
            if paper is None:
                raise ResourceNotFoundError(
                    f"Paper {paper_id} was not found in project {project_id}"
                )
            question_scores = SemanticScoreRepository(session).get_for_paper(
                project_id,
                paper_id,
            )
            return PaperDetails(paper=paper, question_scores=question_scores)
