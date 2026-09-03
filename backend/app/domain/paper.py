from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass(slots=True)
class ExternalIdentifier:
    """
    Внешний identifier глобальной статьи.

    Attributes:
        paper_id (UUID): Идентификатор глобальной Paper.
        provider (str): Имя scientific provider.
        value (str): Значение identifier.

    Fallbacks:
        Пустые значения должны отбрасываться provider mapper.
    """

    paper_id: UUID
    provider: str
    value: str


@dataclass(slots=True)
class Paper:
    """
    Глобальная научная статья, общая для всех проектов.

    Attributes:
        title (str): Каноническое название статьи.
        semantic_scholar_id (str | None): Semantic Scholar paper ID.
        id (UUID): Внутренний глобальный ID.

    Fallbacks:
        Неполные provider metadata представлены None или пустыми collections.
    """

    title: str
    semantic_scholar_id: str | None = None
    abstract: str | None = None
    year: int | None = None
    citation_count: int | None = None
    influential_citation_count: int | None = None
    reference_count: int | None = None
    authors: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    pdf_url: str | None = None
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class ProviderPaper:
    """
    Нормализованный ответ scholarly provider до persistence.

    Attributes:
        paper_id (str): Канонический provider paper ID.
        title (str): Каноническое название.
        external_ids (dict[str, str]): Доступные внешние identifiers.

    Fallbacks:
        Missing abstract, year, PDF и counts сохраняются как None.
    """

    paper_id: str
    title: str
    external_ids: dict[str, str]
    abstract: str | None = None
    year: int | None = None
    citation_count: int | None = None
    influential_citation_count: int | None = None
    reference_count: int | None = None
    authors: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    pdf_url: str | None = None
