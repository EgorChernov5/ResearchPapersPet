from functools import lru_cache

from pydantic import Field, model_validator
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
        document_storage_backend (str): Активный backend: local или s3.
        document_storage_local_root (str): Корень local object storage.
        document_storage_max_bytes (int): Максимальный размер PDF.
        document_storage_s3_bucket (str): Bucket production/RustFS storage.
        arxiv_pdf_base_url (str): Базовый URL arXiv PDF endpoint.
        arxiv_user_agent (str): Идентификатор клиента для arXiv requests.

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
    document_storage_backend: str = Field(default="local", pattern="^(local|s3)$")
    document_storage_local_root: str = "./data/document-storage"
    document_storage_max_bytes: int = Field(default=50_000_000, gt=0)
    document_storage_s3_bucket: str = "research-documents"
    document_storage_s3_endpoint_url: str | None = None
    document_storage_s3_region: str = "us-east-1"
    document_storage_s3_access_key_id: str | None = None
    document_storage_s3_secret_access_key: str | None = None
    arxiv_pdf_base_url: str = "https://export.arxiv.org/pdf"
    arxiv_download_timeout_seconds: float = Field(default=30.0, gt=0)
    arxiv_download_max_retries: int = Field(default=3, ge=1)
    arxiv_user_agent: str = "ResearchPapersPet/0.1 (mailto:research@example.com)"

    @model_validator(mode="after")
    def validate_document_storage(self) -> "Settings":
        """
        Проверяет согласованность настроек выбранного storage backend.

        Returns:
            Settings: Проверенная конфигурация.

        Fallbacks:
            Пустой bucket и неполная пара credentials отклоняются при startup.
        """

        # Require a usable target and never accept only half of a static credential pair.
        if self.document_storage_backend == "local" and not (
            self.document_storage_local_root.strip()
        ):
            raise ValueError("Local document storage root must not be empty")
        if self.document_storage_backend == "s3" and not self.document_storage_s3_bucket.strip():
            raise ValueError("S3 document storage bucket must not be empty")
        if self.document_storage_backend == "s3" and not self.document_storage_s3_region.strip():
            raise ValueError("S3 document storage region must not be empty")
        credentials = (
            self.document_storage_s3_access_key_id,
            self.document_storage_s3_secret_access_key,
        )
        if any(credentials) and not all(credentials):
            raise ValueError("S3 access key and secret key must be configured together")
        if not self.arxiv_pdf_base_url.strip() or not self.arxiv_user_agent.strip():
            raise ValueError("arXiv base URL and User-Agent must not be empty")
        return self


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
