import asyncio
from urllib.parse import quote

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings
from app.constants import SEMANTIC_SCHOLAR_PAPER_FIELDS
from app.domain.paper import ProviderPaper
from app.providers.base import (
    ScholarlyPaperNotFoundError,
    ScholarlyProvider,
    ScholarlyProviderError,
)


class SemanticScholarTransientError(ScholarlyProviderError):
    """
    Временная Semantic Scholar ошибка, допускающая retry.

    Fallbacks:
        После исчерпания retries ошибка передаётся research layer.
    """


class SemanticScholarProvider(ScholarlyProvider):
    """
    Async adapter для Semantic Scholar Academic Graph API.

    Attributes:
        base_url (str): Base URL Graph API.
        timeout (float): HTTP timeout в секундах.
        max_retries (int): Максимальное число transport attempts.

    Fallbacks:
        Timeout, 429 и 5xx повторяются с exponential backoff и затем становятся понятной ошибкой.
    """

    def __init__(self, config: Settings, client: httpx.AsyncClient | None = None) -> None:
        """
        Создаёт provider с optional injected HTTP client.

        Parameters:
            config (Settings): Настройки API key, URL, timeout и retries.
            client (httpx.AsyncClient | None): Клиент для reuse или тестов. По умолчанию: None.

        Returns:
            None: Метод инициализирует adapter.

        Fallbacks:
            Без injected client provider создаёт и затем закрывает собственный client.
        """

        self.base_url = config.semantic_scholar_base_url.rstrip("/")
        self.timeout = config.semantic_scholar_timeout_seconds
        self.max_retries = config.semantic_scholar_max_retries
        headers = {"Accept": "application/json"}
        if config.semantic_scholar_api_key:
            headers["x-api-key"] = config.semantic_scholar_api_key
        self.client = client or httpx.AsyncClient(headers=headers, timeout=self.timeout)
        self.owns_client = client is None

    async def close(self) -> None:
        """
        Закрывает созданный provider HTTP client.

        Returns:
            None: Сетевые ресурсы освобождаются.

        Fallbacks:
            Injected client остаётся во владении вызывающего кода.
        """

        if self.owns_client:
            await self.client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_payload: dict | list | None = None,
    ) -> dict | list:
        """
        Выполняет один Semantic Scholar request с retry policy.

        Parameters:
            method (str): HTTP method.
            path (str): Relative Graph API path.
            params (dict | None): Query parameters. По умолчанию: None.
            json_payload (dict | list | None): JSON body. По умолчанию: None.

        Returns:
            dict | list: Декодированный JSON response.

        Fallbacks:
            Timeout, network errors, 429 и 5xx повторяются; 404 имеет отдельную ошибку.
        """

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            retry=retry_if_exception_type(SemanticScholarTransientError),
            reraise=True,
        ):
            with attempt:
                try:
                    response = await self.client.request(
                        method,
                        f"{self.base_url}/{path.lstrip('/')}",
                        params=params,
                        json=json_payload,
                        timeout=self.timeout,
                    )
                except (httpx.TimeoutException, httpx.NetworkError) as error:
                    raise SemanticScholarTransientError(
                        f"Semantic Scholar request failed: {error}"
                    ) from error

                # Respect an explicit rate-limit delay before the retry backoff.
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "0")
                    try:
                        delay = min(max(float(retry_after), 0.0), 30.0)
                    except ValueError:
                        delay = 0.0
                    if delay:
                        await asyncio.sleep(delay)
                    raise SemanticScholarTransientError("Semantic Scholar rate limit exceeded")
                if response.status_code >= 500:
                    raise SemanticScholarTransientError(
                        f"Semantic Scholar returned HTTP {response.status_code}"
                    )
                if response.status_code == 404:
                    raise ScholarlyPaperNotFoundError("Semantic Scholar paper was not found")
                if response.is_error:
                    raise ScholarlyProviderError(
                        f"Semantic Scholar returned HTTP {response.status_code}: "
                        f"{response.text[:300]}"
                    )
                try:
                    return response.json()
                except ValueError as error:
                    raise ScholarlyProviderError(
                        "Semantic Scholar returned invalid JSON"
                    ) from error

        raise SemanticScholarTransientError("Semantic Scholar retry policy was exhausted")

    def _map_paper(self, payload: dict) -> ProviderPaper:
        """
        Преобразует Semantic Scholar JSON в provider-neutral DTO.

        Parameters:
            payload (dict): Одна API paper object.

        Returns:
            ProviderPaper: Нормализованные metadata.

        Fallbacks:
            Missing optional fields становятся None или пустыми collections.
        """

        paper_id = payload.get("paperId")
        title = payload.get("title")
        if not paper_id or not title:
            raise ScholarlyProviderError("Semantic Scholar paper has no paperId or title")

        # Normalize provider-specific nested metadata at the adapter boundary.
        external_ids = {
            str(key).lower(): str(value)
            for key, value in (payload.get("externalIds") or {}).items()
            if value
        }
        authors = [
            str(author["name"]).strip()
            for author in (payload.get("authors") or [])
            if author.get("name")
        ]
        categories = [
            str(item["category"]).strip()
            for item in (payload.get("s2FieldsOfStudy") or [])
            if item.get("category")
        ]
        open_access_pdf = payload.get("openAccessPdf") or {}
        return ProviderPaper(
            paper_id=str(paper_id),
            title=str(title).strip(),
            external_ids=external_ids,
            abstract=payload.get("abstract"),
            year=payload.get("year"),
            citation_count=payload.get("citationCount"),
            influential_citation_count=payload.get("influentialCitationCount"),
            reference_count=payload.get("referenceCount"),
            authors=authors,
            categories=categories,
            pdf_url=open_access_pdf.get("url"),
        )

    async def resolve_paper(
        self,
        identifier: str | None = None,
        title: str | None = None,
        year: int | None = None,
    ) -> ProviderPaper | None:
        """
        Выполняет простой provider lookup для application use cases.

        Parameters:
            identifier (str | None): Canonical identifier. По умолчанию: None.
            title (str | None): Title fallback. По умолчанию: None.
            year (int | None): Optional year filter. По умолчанию: None.

        Returns:
            ProviderPaper | None: Найденная статья или None.

        Fallbacks:
            Отсутствующий ID переключает lookup на title search.
        """

        if identifier:
            try:
                return await self.get_paper(identifier)
            except ScholarlyPaperNotFoundError:
                if not title:
                    return None
        if title:
            papers = await self.search_papers(title, limit=1, year=year)
            return papers[0] if papers else None
        return None

    async def get_paper(self, identifier: str) -> ProviderPaper:
        """
        Получает одну статью по Semantic Scholar или external ID.

        Parameters:
            identifier (str): Canonical или prefixed external identifier.

        Returns:
            ProviderPaper: Нормализованные metadata.

        Fallbacks:
            404 преобразуется в ScholarlyPaperNotFoundError.
        """

        fields = ",".join(SEMANTIC_SCHOLAR_PAPER_FIELDS)
        payload = await self._request(
            "GET",
            f"paper/{quote(identifier, safe='')}",
            params={"fields": fields},
        )
        if not isinstance(payload, dict):
            raise ScholarlyProviderError("Semantic Scholar returned an invalid paper object")
        return self._map_paper(payload)

    async def get_papers_batch(self, identifiers: list[str]) -> list[ProviderPaper]:
        """
        Получает статьи batches до API limit 500.

        Parameters:
            identifiers (list[str]): Canonical identifiers.

        Returns:
            list[ProviderPaper]: Найденные статьи без null results.

        Fallbacks:
            Пустой вход не вызывает внешний API.
        """

        if not identifiers:
            return []

        # Respect Semantic Scholar batch size while preserving input order.
        fields = ",".join(SEMANTIC_SCHOLAR_PAPER_FIELDS)
        papers = []
        for offset in range(0, len(identifiers), 500):
            payload = await self._request(
                "POST",
                "paper/batch",
                params={"fields": fields},
                json_payload={"ids": identifiers[offset : offset + 500]},
            )
            if not isinstance(payload, list):
                raise ScholarlyProviderError("Semantic Scholar returned an invalid batch")
            papers.extend(self._map_paper(item) for item in payload if item)
        return papers

    async def search_papers(
        self,
        query: str,
        limit: int = 10,
        year: int | None = None,
    ) -> list[ProviderPaper]:
        """
        Ищет статьи по title query с pagination.

        Parameters:
            query (str): Поисковая строка.
            limit (int): Максимальное число результатов. По умолчанию: 10.
            year (int | None): Optional publication year. По умолчанию: None.

        Returns:
            list[ProviderPaper]: Нормализованные результаты.

        Fallbacks:
            Пустой query или non-positive limit возвращает пустой список.
        """

        if not query.strip() or limit <= 0:
            return []

        # Fetch bounded pages so the provider never downloads an unbounded result set.
        fields = ",".join(SEMANTIC_SCHOLAR_PAPER_FIELDS)
        papers = []
        offset = 0
        while len(papers) < limit:
            page_size = min(100, limit - len(papers))
            params = {
                "query": query.strip(),
                "limit": page_size,
                "offset": offset,
                "fields": fields,
            }
            if year is not None:
                params["year"] = str(year)
            payload = await self._request("GET", "paper/search", params=params)
            if not isinstance(payload, dict):
                raise ScholarlyProviderError("Semantic Scholar returned an invalid search page")
            data = payload.get("data") or []
            papers.extend(self._map_paper(item) for item in data if item)
            if len(data) < page_size or "next" not in payload:
                break
            offset = int(payload["next"])
        return papers[:limit]

    async def get_references(self, paper_id: str, limit: int = 1000) -> list[ProviderPaper]:
        """
        Получает paginated references статьи.

        Parameters:
            paper_id (str): Semantic Scholar source paper ID.
            limit (int): Максимальное число references. По умолчанию: 1000.

        Returns:
            list[ProviderPaper]: Нормализованные cited papers.

        Fallbacks:
            Missing citedPaper records пропускаются.
        """

        return await self._get_neighbors(paper_id, "references", "citedPaper", limit)

    async def get_citations(self, paper_id: str, limit: int = 1000) -> list[ProviderPaper]:
        """
        Получает paginated citations статьи.

        Parameters:
            paper_id (str): Semantic Scholar target paper ID.
            limit (int): Максимальное число citations. По умолчанию: 1000.

        Returns:
            list[ProviderPaper]: Нормализованные citing papers.

        Fallbacks:
            Missing citingPaper records пропускаются.
        """

        return await self._get_neighbors(paper_id, "citations", "citingPaper", limit)

    async def _get_neighbors(
        self,
        paper_id: str,
        direction: str,
        payload_key: str,
        limit: int,
    ) -> list[ProviderPaper]:
        """
        Загружает bounded paginated citation neighborhood.

        Parameters:
            paper_id (str): Semantic Scholar paper ID.
            direction (str): API path references или citations.
            payload_key (str): Nested paper key в API response.
            limit (int): Максимальное число neighbors.

        Returns:
            list[ProviderPaper]: Нормализованные neighbor papers.

        Fallbacks:
            Non-positive limit возвращает пустой список без API request.
        """

        if limit <= 0:
            return []

        # Iterate by API offset until the configured neighborhood bound is reached.
        fields = ",".join(SEMANTIC_SCHOLAR_PAPER_FIELDS)
        papers = []
        offset = 0
        while len(papers) < limit:
            page_size = min(1000, limit - len(papers))
            payload = await self._request(
                "GET",
                f"paper/{quote(paper_id, safe='')}/{direction}",
                params={"fields": fields, "limit": page_size, "offset": offset},
            )
            if not isinstance(payload, dict):
                raise ScholarlyProviderError("Semantic Scholar returned an invalid citation page")
            data = payload.get("data") or []
            papers.extend(
                self._map_paper(item[payload_key]) for item in data if item.get(payload_key)
            )
            if len(data) < page_size or "next" not in payload:
                break
            offset = int(payload["next"])
        return papers[:limit]
