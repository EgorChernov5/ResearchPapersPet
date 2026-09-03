from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from app.api.structures import ResearchJobResponse
from app.application.exceptions import ResourceNotFoundError
from app.application.get_research_status import GetResearchStatus

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/{job_id}", response_model=ResearchJobResponse)
def get_research_status(job_id: UUID, request: Request) -> ResearchJobResponse:
    """
    Возвращает progress и terminal state background job.

    Parameters:
        job_id (UUID): Идентификатор job из path.
        request (Request): FastAPI request с database state.

    Returns:
        ResearchJobResponse: Текущее persistent job state.

    Fallbacks:
        Missing job возвращает HTTP 404.
    """

    try:
        job = GetResearchStatus(request.app.state.database.session_factory).execute(job_id)
    except ResourceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return ResearchJobResponse.model_validate(job)
