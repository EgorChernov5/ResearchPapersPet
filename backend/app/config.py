from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Конфигурация приложения из переменных окружения.

    Attributes:
        frontend_origin (str): Разрешённый browser origin frontend.
        app_name (str): Имя FastAPI-приложения.
        database_url (str): Строка подключения к PostgreSQL.
        redis_url (str): Строка подключения к Redis.
        semantic_scholar_api_key (str | None): API-ключ Semantic Scholar.
        embedding_model_name (str): Hugging Face или local model identifier.
        embedding_model_version (str): Версия persistence cache contract.
        embedding_dimensions (int): Размерность vector column. По умолчанию: 768.
        embedding_batch_size (int): Размер inference batch. По умолчанию: 16.
        related_work_max_bytes (int): Максимальный upload size. По умолчанию: 10000000.

    Fallbacks:
        Для локальной разработки используются адреса localhost без секретов.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Scientific Research Graph"
    frontend_origin: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://research:research@127.0.0.1:55432/research_graph"
    redis_url: str = "redis://localhost:6379/0"
    semantic_scholar_api_key: str | None = None
    semantic_scholar_base_url: str = "https://api.semanticscholar.org/graph/v1"
    semantic_scholar_timeout_seconds: float = Field(default=20.0, gt=0)
    semantic_scholar_max_retries: int = Field(default=4, ge=1)
    embedding_model_name: str = "sentence-transformers/allenai-specter"
    embedding_model_version: str = "1"
    embedding_dimensions: int = Field(default=768, gt=0)
    embedding_batch_size: int = Field(default=16, gt=0)
    related_work_max_bytes: int = Field(default=10_000_000, gt=0)
    worker_queue_name: str = "research_jobs"


@lru_cache
def settings() -> Settings:
    """
    Возвращает единственный объект настроек процесса.

    Returns:
        Settings: Загруженная конфигурация приложения.

    Fallbacks:
        Значения по умолчанию применяются, если переменные окружения отсутствуют.
    """

    return Settings()
