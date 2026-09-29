from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.projects import router as projects_router
from app.api.research import router as research_router
from app.api.results import router as results_router
from app.config import settings
from app.infrastructure.database import Database
from app.infrastructure.document_storage import create_document_storage
from app.infrastructure.redis import RedisConnection


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """
    Создаёт и освобождает application infrastructure.

    Parameters:
        application (FastAPI): FastAPI application instance.

    Returns:
        AsyncIterator[None]: Lifespan context для ASGI server.

    Fallbacks:
        Фактические connection errors сообщает readiness endpoint.
    """

    # Initialize lazy clients once per API process.
    config = settings()
    application.state.database = Database(config)
    application.state.redis = RedisConnection(config)
    application.state.document_storage = create_document_storage(config)
    yield

    # Release connection pools during graceful shutdown.
    application.state.redis.close()
    application.state.database.dispose()


# Compose the HTTP application and allow the configured browser frontend.
config = settings()
app = FastAPI(title=config.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(projects_router)
app.include_router(research_router)
app.include_router(results_router)
