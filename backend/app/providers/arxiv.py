import asyncio
from hashlib import sha256
from urllib.parse import quote

import httpx

from app.providers.structures import DownloadedDocument


class ArxivDocumentUnavailableError(ValueError):
    """
    Обозначает отсутствие пригодного PDF в arXiv.

    Attributes:
        args (tuple): Диагностические аргументы ошибки.

    Fallbacks:
        Application layer выбирает UNAVAILABLE или AWAITING_UPLOAD.
    """


class ArxivDownloadError(RuntimeError):
    """
    Обозначает временную или инфраструктурную ошибку загрузки.

    Attributes:
        args (tuple): Диагностические аргументы ошибки.

    Fallbacks:
        Application layer переводит только текущий DocumentJob в FAILED.
    """


class ArxivPdfDownloader:
    """
    Загружает arXiv PDF с redirect, timeout, retry и streaming size limit.

    Attributes:
        base_url (str): Базовый URL PDF endpoint.
        max_bytes (int): Максимальный размер ответа.
        max_retries (int): Число HTTP-попыток.

    Fallbacks:
        404 и invalid PDF считаются недоступным automatic source.
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        max_retries: int,
        max_bytes: int,
        user_agent: str,
    ) -> None:
        """
        Создаёт downloader с явными transport limits.

        Parameters:
            base_url (str): Базовый URL PDF endpoint.
            timeout_seconds (float): Timeout одной попытки.
            max_retries (int): Число попыток.
            max_bytes (int): Максимальный размер PDF.
            user_agent (str): Идентифицирующий User-Agent.

        Returns:
            None: Метод сохраняет настройки и создаёт HTTP client.

        Fallbacks:
            Неположительные limits отклоняются до network request.
        """

        if timeout_seconds <= 0 or max_retries < 1 or max_bytes <= 0:
            raise ValueError("arXiv download limits must be positive")
        if not user_agent.strip():
            raise ValueError("arXiv User-Agent must not be empty")
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.max_bytes = max_bytes
        self.client = httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        )

    async def download(self, arxiv_id: str) -> DownloadedDocument:
        """
        Загружает и проверяет один canonical arXiv PDF.

        Parameters:
            arxiv_id (str): Canonical identifier без ARXIV prefix.

        Returns:
            DownloadedDocument: PDF bytes, media type и checksum.

        Fallbacks:
            404/invalid content дают ArxivDocumentUnavailableError, exhausted retry — error.
        """

        # Encode legacy identifiers safely while retaining the slash used by old arXiv IDs.
        normalized_id = arxiv_id.strip()
        if normalized_id.casefold().startswith("arxiv:"):
            normalized_id = normalized_id.split(":", 1)[1]
        if not normalized_id:
            raise ArxivDocumentUnavailableError("Paper has no canonical arXiv identifier")
        url = f"{self.base_url}/{quote(normalized_id, safe='/')}.pdf"

        # Retry only transient transport and server failures; consume the body with a hard limit.
        for attempt in range(1, self.max_retries + 1):
            try:
                async with self.client.stream("GET", url) as response:
                    if response.status_code == 404:
                        raise ArxivDocumentUnavailableError(
                            f"arXiv PDF {normalized_id} was not found"
                        )
                    if response.status_code >= 500:
                        raise ArxivDownloadError(
                            f"arXiv returned transient HTTP {response.status_code}"
                        )
                    if response.status_code != 200:
                        raise ArxivDocumentUnavailableError(
                            f"arXiv returned HTTP {response.status_code}"
                        )
                    declared_size = response.headers.get("Content-Length")
                    if declared_size and int(declared_size) > self.max_bytes:
                        raise ArxivDocumentUnavailableError(
                            f"arXiv PDF exceeds configured limit {self.max_bytes}"
                        )
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > self.max_bytes:
                            raise ArxivDocumentUnavailableError(
                                f"arXiv PDF exceeds configured limit {self.max_bytes}"
                            )
                    media_type = response.headers.get("Content-Type", "").split(";", 1)[0]
                    if media_type.casefold() != "application/pdf" or not content.startswith(
                        b"%PDF-"
                    ):
                        raise ArxivDocumentUnavailableError(
                            "arXiv response is not a valid application/pdf document"
                        )
                    payload = bytes(content)
                    return DownloadedDocument(
                        payload,
                        "application/pdf",
                        sha256(payload).hexdigest(),
                    )
            except ArxivDocumentUnavailableError:
                raise
            except (httpx.TimeoutException, httpx.TransportError, ArxivDownloadError) as error:
                if attempt == self.max_retries:
                    raise ArxivDownloadError(
                        f"arXiv PDF download failed after {self.max_retries} attempts: {error}"
                    ) from error
                await asyncio.sleep(0.25 * attempt)
        raise ArxivDownloadError("arXiv PDF download exhausted without a response")

    async def close(self) -> None:
        """
        Закрывает HTTP connection pool.

        Returns:
            None: Все соединения освобождены.

        Fallbacks:
            Повторное закрытие допускается httpx.
        """

        await self.client.aclose()
