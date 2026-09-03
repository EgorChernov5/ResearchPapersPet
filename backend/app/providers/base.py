from abc import ABC, abstractmethod

from app.domain.paper import ProviderPaper


class ScholarlyProviderError(RuntimeError):
    """
    Базовая понятная ошибка scholarly provider.

    Fallbacks:
        Research pipeline записывает failure конкретной paper или job stage.
    """


class ScholarlyPaperNotFoundError(ScholarlyProviderError):
    """
    Запрошенная статья отсутствует у provider.

    Fallbacks:
        Seed resolver продолжает title-based fallback или фиксирует unresolved seed.
    """


class ScholarlyProvider(ABC):
    """
    Минимальный контракт scientific provider без HTTP-деталей.

    Fallbacks:
        Конкретные adapters переводят transport errors в ScholarlyProviderError.
    """

    @abstractmethod
    async def get_paper(self, identifier: str) -> ProviderPaper:
        """
        Получает одну статью по canonical identifier.

        Parameters:
            identifier (str): Provider ID или prefixed external ID.

        Returns:
            ProviderPaper: Нормализованные metadata.

        Fallbacks:
            ScholarlyPaperNotFoundError означает отсутствие статьи.
        """

    @abstractmethod
    async def get_papers_batch(self, identifiers: list[str]) -> list[ProviderPaper]:
        """
        Получает metadata нескольких статей.

        Parameters:
            identifiers (list[str]): Canonical identifiers.

        Returns:
            list[ProviderPaper]: Найденные статьи без missing items.

        Fallbacks:
            Пустой вход возвращает пустой список.
        """

    @abstractmethod
    async def search_papers(
        self,
        query: str,
        limit: int = 10,
        year: int | None = None,
    ) -> list[ProviderPaper]:
        """
        Ищет статьи по title query и optional year.

        Parameters:
            query (str): Поисковая строка.
            limit (int): Максимальное число результатов. По умолчанию: 10.
            year (int | None): Фильтр года публикации. По умолчанию: None.

        Returns:
            list[ProviderPaper]: Нормализованные результаты поиска.

        Fallbacks:
            Отсутствие совпадений возвращает пустой список.
        """

    @abstractmethod
    async def get_references(self, paper_id: str, limit: int = 1000) -> list[ProviderPaper]:
        """
        Получает статьи, на которые ссылается source paper.

        Parameters:
            paper_id (str): Semantic provider ID source paper.
            limit (int): Максимальное число результатов. По умолчанию: 1000.

        Returns:
            list[ProviderPaper]: Нормализованные target papers.

        Fallbacks:
            Пустое neighborhood возвращает пустой список.
        """

    @abstractmethod
    async def get_citations(self, paper_id: str, limit: int = 1000) -> list[ProviderPaper]:
        """
        Получает статьи, цитирующие target paper.

        Parameters:
            paper_id (str): Semantic provider ID target paper.
            limit (int): Максимальное число результатов. По умолчанию: 1000.

        Returns:
            list[ProviderPaper]: Нормализованные source papers.

        Fallbacks:
            Пустое neighborhood возвращает пустой список.
        """
