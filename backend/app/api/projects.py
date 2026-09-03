from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from redis.exceptions import RedisError

from app.api.structures import (
    CreateProjectRequest,
    RelatedWorkUploadResponse,
    ResearchJobResponse,
    ResearchProjectResponse,
    ResearchQuestionResponse,
    ResearchQuestionsRequest,
    ResearchQuestionsResponse,
)
from app.application.exceptions import ResourceNotFoundError
from app.application.projects import AddResearchQuestions, CreateProject, GetProject
from app.application.start_research import StartResearch
from app.application.upload_related_work import UploadRelatedWork
from app.config import settings
from app.domain.project import ResearchConfig
from app.research.related_work_parser import RelatedWorkParseError, RelatedWorkParser

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ResearchProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(payload: CreateProjectRequest, request: Request) -> ResearchProjectResponse:
    """
    Создаёт research project с configuration.

    Parameters:
        payload (CreateProjectRequest): Проверенный HTTP body.
        request (Request): FastAPI request с database state.

    Returns:
        ResearchProjectResponse: Созданный project setup.

    Fallbacks:
        Cross-field config validation возвращает HTTP 422.
    """

    try:
        config = ResearchConfig(**payload.config.model_dump())
        project = CreateProject(request.app.state.database.session_factory).execute(
            payload.name,
            config,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return ResearchProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ResearchProjectResponse)
def get_project(project_id: UUID, request: Request) -> ResearchProjectResponse:
    """
    Возвращает project configuration и questions.

    Parameters:
        project_id (UUID): Идентификатор проекта из path.
        request (Request): FastAPI request с database state.

    Returns:
        ResearchProjectResponse: Project setup.

    Fallbacks:
        Missing project возвращает HTTP 404.
    """

    try:
        project = GetProject(request.app.state.database.session_factory).execute(project_id)
    except ResourceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return ResearchProjectResponse.model_validate(project)


@router.post(
    "/{project_id}/questions",
    response_model=ResearchQuestionsResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_questions(
    project_id: UUID,
    payload: ResearchQuestionsRequest,
    request: Request,
) -> ResearchQuestionsResponse:
    """
    Добавляет research questions к проекту.

    Parameters:
        project_id (UUID): Идентификатор проекта из path.
        payload (ResearchQuestionsRequest): Список вопросов.
        request (Request): FastAPI request с database state.

    Returns:
        ResearchQuestionsResponse: Созданные question entities.

    Fallbacks:
        Missing project возвращает 404, invalid question — 422.
    """

    try:
        questions = AddResearchQuestions(request.app.state.database.session_factory).execute(
            project_id,
            payload.questions,
        )
    except ResourceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return ResearchQuestionsResponse(
        questions=[ResearchQuestionResponse.model_validate(question) for question in questions]
    )


@router.post("/{project_id}/related-work", response_model=RelatedWorkUploadResponse)
async def upload_related_work(
    project_id: UUID,
    file: UploadFile,
    request: Request,
) -> RelatedWorkUploadResponse:
    """
    Загружает и сохраняет XLSX/CSV Related Work.

    Parameters:
        project_id (UUID): Идентификатор проекта из path.
        file (UploadFile): Multipart upload.
        request (Request): FastAPI request с infrastructure state.

    Returns:
        RelatedWorkUploadResponse: Число сохранённых entries.

    Fallbacks:
        Oversized, invalid или unsupported file возвращает HTTP 413/422.
    """

    config = settings()
    content = await file.read(config.related_work_max_bytes + 1)
    if len(content) > config.related_work_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Related Work file exceeds {config.related_work_max_bytes} bytes",
        )
    try:
        entries = UploadRelatedWork(
            request.app.state.database.session_factory,
            RelatedWorkParser(),
        ).execute(
            project_id,
            content,
            file.filename or "",
        )
    except ResourceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except RelatedWorkParseError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return RelatedWorkUploadResponse(project_id=project_id, entries_count=len(entries))


@router.post(
    "/{project_id}/research",
    response_model=ResearchJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_research(project_id: UUID, request: Request) -> ResearchJobResponse:
    """
    Создаёт background ResearchJob и ставит его в Redis queue.

    Parameters:
        project_id (UUID): Идентификатор проекта из path.
        request (Request): FastAPI request с database и Redis state.

    Returns:
        ResearchJobResponse: Job в статусе PENDING.

    Fallbacks:
        Incomplete project возвращает 422; queue failure — 503.
    """

    try:
        job = StartResearch(
            request.app.state.database.session_factory,
            request.app.state.redis.client,
            settings().worker_queue_name,
        ).execute(project_id)
    except ResourceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except RedisError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis queue is unavailable: {error}",
        ) from error
    return ResearchJobResponse.model_validate(job)
