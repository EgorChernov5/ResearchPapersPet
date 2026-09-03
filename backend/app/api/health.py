from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import text

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness() -> dict[str, str]:
    """
    Проверяет работоспособность FastAPI process без dependencies.

    Returns:
        dict[str, str]: Статус process.

    Fallbacks:
        Endpoint остаётся доступным при недоступных PostgreSQL или Redis.
    """

    return {"status": "ok"}


@router.get("/ready")
def readiness(request: Request) -> dict[str, str]:
    """
    Проверяет подключения к PostgreSQL и Redis.

    Parameters:
        request (Request): FastAPI request с application state.

    Returns:
        dict[str, str]: Статусы обязательных dependencies.

    Fallbacks:
        HTTP 503 возвращается с понятной причиной недоступности.
    """

    # Verify both stateful dependencies before advertising readiness.
    try:
        with request.app.state.database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"PostgreSQL is unavailable: {error}",
        ) from error
    try:
        request.app.state.redis.client.ping()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis is unavailable: {error}",
        ) from error
    return {"status": "ok", "postgres": "ok", "redis": "ok"}
