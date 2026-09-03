from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from app.api.structures import (
    GraphEdgeResponse,
    GraphResponse,
    PaperDetailsResponse,
    PaperListResponse,
    PaperQuestionScoreResponse,
    PaperResponse,
)
from app.application.exceptions import ResourceNotFoundError
from app.application.get_graph import GetResearchGraph
from app.application.get_ranking import GetPaperDetails, GetPaperRanking

router = APIRouter(prefix="/projects/{project_id}", tags=["results"])


@router.get("/papers", response_model=PaperListResponse)
def get_papers(
    project_id: UUID,
    request: Request,
    min_topic_score: float | None = None,
    min_final_score: float | None = None,
    min_year: int | None = None,
    min_citations: int | None = None,
    max_depth: int | None = None,
    category: str | None = None,
    is_seed: bool | None = None,
) -> PaperListResponse:
    """
    Возвращает metadata всех project papers с optional filters.

    Parameters:
        project_id (UUID): Идентификатор проекта из path.
        request (Request): FastAPI request с database state.
        min_topic_score (float | None): Минимальный topic score.
        min_final_score (float | None): Минимальный final score.
        min_year (int | None): Минимальный publication year.
        min_citations (int | None): Минимальный citation count.
        max_depth (int | None): Максимальная discovery depth.
        category (str | None): Требуемая category.
        is_seed (bool | None): Seed/discovered filter.

    Returns:
        PaperListResponse: Отфильтрованные paper views.

    Fallbacks:
        Missing project возвращает HTTP 404.
    """

    try:
        papers = GetPaperRanking(request.app.state.database.session_factory).execute(
            project_id=project_id,
            min_topic_score=min_topic_score,
            min_final_score=min_final_score,
            min_year=min_year,
            min_citations=min_citations,
            max_depth=max_depth,
            category=category,
            is_seed=is_seed,
            sort_by="title",
            descending=False,
        )
    except ResourceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return PaperListResponse(
        count=len(papers),
        papers=[PaperResponse.model_validate(paper) for paper in papers],
    )


@router.get("/papers/{paper_id}", response_model=PaperDetailsResponse)
def get_paper_details(
    project_id: UUID,
    paper_id: UUID,
    request: Request,
) -> PaperDetailsResponse:
    """
    Возвращает paper metadata, project scores и question similarities.

    Parameters:
        project_id (UUID): Идентификатор проекта из path.
        paper_id (UUID): Идентификатор global paper из path.
        request (Request): FastAPI request с database state.

    Returns:
        PaperDetailsResponse: Полная project paper view.

    Fallbacks:
        Paper вне проекта возвращает HTTP 404.
    """

    try:
        details = GetPaperDetails(request.app.state.database.session_factory).execute(
            project_id,
            paper_id,
        )
    except ResourceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return PaperDetailsResponse(
        paper=PaperResponse.model_validate(details.paper),
        question_scores=[
            PaperQuestionScoreResponse.model_validate(score) for score in details.question_scores
        ],
    )


@router.get("/ranking", response_model=PaperListResponse)
def get_ranking(
    project_id: UUID,
    request: Request,
    min_topic_score: float | None = None,
    min_final_score: float | None = None,
    min_year: int | None = None,
    min_citations: int | None = None,
    max_depth: int | None = None,
    category: str | None = None,
    is_seed: bool | None = None,
    sort_by: str = "final_score",
    descending: bool = True,
) -> PaperListResponse:
    """
    Возвращает sorted ranking без повторного research pipeline.

    Parameters:
        project_id (UUID): Идентификатор проекта из path.
        request (Request): FastAPI request с database state.
        min_topic_score (float | None): Минимальный topic score.
        min_final_score (float | None): Минимальный final score.
        min_year (int | None): Минимальный publication year.
        min_citations (int | None): Минимальный citation count.
        max_depth (int | None): Максимальная discovery depth.
        category (str | None): Требуемая category.
        is_seed (bool | None): Seed/discovered filter.
        sort_by (str): Ranking field.
        descending (bool): Направление sorting.

    Returns:
        PaperListResponse: Sorted filtered ranking.

    Fallbacks:
        Unsupported sort field возвращает HTTP 422.
    """

    try:
        papers = GetPaperRanking(request.app.state.database.session_factory).execute(
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
    except ResourceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return PaperListResponse(
        count=len(papers),
        papers=[PaperResponse.model_validate(paper) for paper in papers],
    )


@router.get("/graph", response_model=GraphResponse)
def get_graph(
    project_id: UUID,
    request: Request,
    min_topic_score: float | None = None,
    min_final_score: float | None = None,
    min_year: int | None = None,
    min_citations: int | None = None,
    max_depth: int | None = None,
    category: str | None = None,
    is_seed: bool | None = None,
) -> GraphResponse:
    """
    Возвращает filtered graph nodes и internal directed edges.

    Parameters:
        project_id (UUID): Идентификатор проекта из path.
        request (Request): FastAPI request с database state.
        min_topic_score (float | None): Минимальный topic score.
        min_final_score (float | None): Минимальный final score.
        min_year (int | None): Минимальный publication year.
        min_citations (int | None): Минимальный citation count.
        max_depth (int | None): Максимальная discovery depth.
        category (str | None): Требуемая category.
        is_seed (bool | None): Seed/discovered filter.

    Returns:
        GraphResponse: Nodes и edges для visualization client.

    Fallbacks:
        Empty filtered result возвращает пустой graph.
    """

    try:
        graph = GetResearchGraph(request.app.state.database.session_factory).execute(
            project_id=project_id,
            min_topic_score=min_topic_score,
            min_final_score=min_final_score,
            min_year=min_year,
            min_citations=min_citations,
            max_depth=max_depth,
            category=category,
            is_seed=is_seed,
        )
    except ResourceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return GraphResponse(
        nodes=[PaperResponse.model_validate(paper) for paper in graph.papers],
        edges=[
            GraphEdgeResponse(
                source_paper_id=citation.source_paper_id,
                target_paper_id=citation.target_paper_id,
            )
            for citation in graph.citations
        ],
    )
