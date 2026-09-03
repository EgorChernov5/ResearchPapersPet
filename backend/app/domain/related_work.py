from dataclasses import dataclass


@dataclass(slots=True)
class PaperIdentityInput:
    """
    Минимальный вход seed resolver без researcher annotations.

    Attributes:
        local_id (str): Локальный identifier строки.
        title (str): Ожидаемое название статьи.
        year (int | None): Ожидаемый год публикации.
        source (str | None): ID, DOI или URL исходной статьи.

    Fallbacks:
        Resolver использует title search, если source отсутствует.
    """

    local_id: str
    title: str
    year: int | None
    source: str | None


@dataclass(slots=True)
class RelatedWorkEntry:
    """
    Строка Related Work вместе с researcher annotations.

    Attributes:
        local_id (str): Локальный ID seed paper.
        title (str): Название статьи.
        year (int | None): Год публикации.
        source (str | None): Ссылка или внешний identifier.

    Fallbacks:
        Необязательные annotations сохраняются как None.
    """

    local_id: str
    title: str
    year: int | None
    source: str | None
    venue: str | None = None
    bibtex_key: str | None = None
    literature_block: str | None = None
    task: str | None = None
    method: str | None = None
    datasets: str | None = None
    metrics: str | None = None
    code_available: str | None = None
    data_available: str | None = None
    usefulness: str | None = None
    comparison_ideas: str | None = None

    def to_identity_input(self) -> PaperIdentityInput:
        """
        Отделяет identification fields от researcher annotations.

        Returns:
            PaperIdentityInput: Минимальный контракт для seed resolver.

        Fallbacks:
            Отсутствующие year и source остаются None для title fallback.
        """

        return PaperIdentityInput(
            local_id=self.local_id,
            title=self.title,
            year=self.year,
            source=self.source,
        )
