import os
import threading
import time
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from app.application.documents import ProcessProjectDocuments
from app.domain.document import DocumentJobStatus
from app.domain.paper import ProviderPaper
from app.domain.project import ResearchConfig
from app.domain.research_job import ResearchJobStatus
from app.infrastructure.database import Base
from app.infrastructure.document_storage import LocalVolumeDocumentStorage
from app.providers.arxiv import (
    ArxivDocumentUnavailableError,
    ArxivDownloadError,
    ArxivPdfDownloader,
)
from app.repositories.documents import DocumentJobRepository
from app.repositories.papers import PaperRepository, ProjectPaperRepository
from app.repositories.projects import ProjectRepository
from app.repositories.research_jobs import ResearchJobRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class ArxivFixtureHandler(BaseHTTPRequestHandler):
    """
    Обслуживает recorded PDF и failure responses через настоящий local HTTP socket.

    Attributes:
        pdf (bytes): Минимальный сохранённый PDF fixture.

    Fallbacks:
        Неизвестный route возвращает 404.
    """

    pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF"
    last_user_agent = ""

    def do_GET(self) -> None:
        """
        Возвращает redirect, PDF, invalid content, oversized или delayed response.

        Returns:
            None: Ответ записывается в HTTP socket.

        Fallbacks:
            Unknown path получает HTTP 404.
        """

        # Expose deterministic branches required by the downloader contract.
        type(self).last_user_agent = self.headers.get("User-Agent", "")
        if self.path == "/pdf/redirect.pdf":
            self.send_response(302)
            self.send_header("Location", "/pdf/fixture.pdf")
            self.end_headers()
            return
        if self.path == "/pdf/fixture.pdf":
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(self.pdf)))
            self.end_headers()
            self.wfile.write(self.pdf)
            return
        if self.path == "/pdf/html.pdf":
            payload = b"<html>not a pdf</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/pdf/large.pdf":
            payload = b"%PDF-1.4\n" + (b"x" * 100)
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/pdf/slow.pdf":
            time.sleep(0.15)
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.end_headers()
            self.wfile.write(self.pdf)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        """
        Отключает шум стандартного HTTP test server.

        Parameters:
            format (str): Формат log message.
            args (object): Аргументы log message.

        Returns:
            None: Сообщение намеренно не выводится.

        Fallbacks:
            Test assertions используют HTTP responses, а не server logs.
        """


@pytest.fixture
def arxiv_server() -> str:
    """
    Запускает local HTTP server на свободном порту.

    Yields:
        str: Базовый URL fixture PDF endpoint.

    Fallbacks:
        Server всегда закрывается после test.
    """

    # Bind port zero so parallel test runs cannot collide.
    server = ThreadingHTTPServer(("127.0.0.1", 0), ArxivFixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/pdf"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.asyncio
async def test_arxiv_downloader_follows_redirect_and_validates_checksum(arxiv_server: str) -> None:
    """
    Проверяет настоящий HTTP redirect, PDF body, User-Agent и checksum pipeline.

    Parameters:
        arxiv_server (str): URL local fixture server.

    Returns:
        None: Assertions подтверждают download contract.

    Fallbacks:
        Client закрывается даже при failed assertion.
    """

    downloader = ArxivPdfDownloader(arxiv_server, 1, 2, 1_000, "ResearchPapersPet/test")
    try:
        downloaded = await downloader.download("redirect")
        assert downloaded.content == ArxivFixtureHandler.pdf
        assert downloaded.media_type == "application/pdf"
        assert downloaded.checksum == sha256(ArxivFixtureHandler.pdf).hexdigest()
        assert ArxivFixtureHandler.last_user_agent == "ResearchPapersPet/test"
    finally:
        await downloader.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", ["missing", "html", "large"])
async def test_arxiv_downloader_rejects_unavailable_content(
    arxiv_server: str,
    identifier: str,
) -> None:
    """
    Проверяет 404, HTML и size limit без mock downloader result.

    Parameters:
        arxiv_server (str): URL local fixture server.
        identifier (str): Failure route identifier.

    Returns:
        None: Каждый response отклонён как unavailable.

    Fallbacks:
        Client закрывается после parametrized branch.
    """

    downloader = ArxivPdfDownloader(arxiv_server, 1, 1, 50, "ResearchPapersPet/test")
    try:
        with pytest.raises(ArxivDocumentUnavailableError):
            await downloader.download(identifier)
    finally:
        await downloader.close()


@pytest.mark.asyncio
async def test_arxiv_downloader_retries_timeout(arxiv_server: str) -> None:
    """
    Проверяет bounded retry при timeout настоящего HTTP server.

    Parameters:
        arxiv_server (str): URL local fixture server.

    Returns:
        None: Exhausted retry даёт typed operational error.

    Fallbacks:
        Client закрывается после timeout.
    """

    downloader = ArxivPdfDownloader(arxiv_server, 0.02, 2, 1_000, "ResearchPapersPet/test")
    try:
        with pytest.raises(ArxivDownloadError, match="after 2 attempts"):
            await downloader.download("slow")
    finally:
        await downloader.close()


@pytest.mark.asyncio
async def test_document_processor_persists_pdf_and_sets_parsing(
    arxiv_server: str,
    tmp_path: Path,
) -> None:
    """
    Проверяет automatic branch с real selector target, HTTP, storage и persistence.

    Parameters:
        arxiv_server (str): URL local fixture server.
        tmp_path (Path): Временный local object storage.

    Returns:
        None: PDF сохранён, job переведена в PARSING.

    Fallbacks:
        SQLite и HTTP resources освобождаются после test.
    """

    # Persist a selected target with a canonical arXiv identifier.
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        project = ProjectRepository(session).create(
            "Document processor",
            ResearchConfig(allow_manual_pdf_upload=True),
        )
        paper = PaperRepository(session).upsert(
            ProviderPaper("fixture-paper", "Fixture Paper", {"arxiv": "fixture"})
        )
        ProjectPaperRepository(session).upsert(project.id, paper.id, True, 0)
        research_job = ResearchJobRepository(session).create(project.id)
        target = DocumentJobRepository(session).create_target(
            project.id,
            paper.id,
            research_job.id,
        )
        session.commit()

    # Exercise the production downloader and local storage as one application path.
    downloader = ArxivPdfDownloader(arxiv_server, 1, 2, 1_000, "ResearchPapersPet/test")
    storage = LocalVolumeDocumentStorage(tmp_path, 1_000)
    try:
        jobs = await ProcessProjectDocuments(sessions, storage, downloader).execute(project.id)
        assert jobs[0].id == target.id
        assert jobs[0].status == DocumentJobStatus.PARSING
        assert jobs[0].document_id is not None
        assert len(list(tmp_path.rglob("*.pdf"))) == 1
    finally:
        await downloader.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_awaiting_upload_does_not_change_completed_research_job(
    arxiv_server: str,
    tmp_path: Path,
) -> None:
    """
    Проверяет non-blocking fallback для missing canonical arXiv identifier.

    Parameters:
        arxiv_server (str): URL local fixture server.
        tmp_path (Path): Временный local object storage.

    Returns:
        None: Document ожидает upload, ResearchJob остаётся COMPLETED.

    Fallbacks:
        Missing identifier не выполняет HTTP request.
    """

    # Complete research before running the independent document branch.
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        project = ProjectRepository(session).create(
            "Awaiting upload",
            ResearchConfig(allow_manual_pdf_upload=True),
        )
        paper = PaperRepository(session).upsert(ProviderPaper("missing-arxiv", "Missing arXiv", {}))
        ProjectPaperRepository(session).upsert(project.id, paper.id, True, 0)
        research_job = ResearchJobRepository(session).create(project.id)
        ResearchJobRepository(session).update(
            research_job.id,
            ResearchJobStatus.COMPLETED,
            1.0,
        )
        DocumentJobRepository(session).create_target(project.id, paper.id, research_job.id)
        session.commit()

    downloader = ArxivPdfDownloader(arxiv_server, 1, 1, 1_000, "ResearchPapersPet/test")
    try:
        jobs = await ProcessProjectDocuments(
            sessions,
            LocalVolumeDocumentStorage(tmp_path, 1_000),
            downloader,
        ).execute(project.id)
        with sessions() as session:
            persisted_research = ResearchJobRepository(session).get(research_job.id)
        assert jobs[0].status == DocumentJobStatus.AWAITING_UPLOAD
        assert persisted_research.status == ResearchJobStatus.COMPLETED
        assert list(tmp_path.rglob("*.pdf")) == []
    finally:
        await downloader.close()
        engine.dispose()


@pytest.mark.external
@pytest.mark.skipif(
    os.getenv("RUN_EXTERNAL_RESEARCH_TESTS") != "1",
    reason="Set RUN_EXTERNAL_RESEARCH_TESTS=1 to call arXiv",
)
@pytest.mark.asyncio
async def test_arxiv_external_downloads_stable_public_pdf() -> None:
    """
    Проверяет один стабильный публичный arXiv PDF через production endpoint.

    Returns:
        None: Response проходит signature, MIME и checksum validation.

    Fallbacks:
        Test пропускается без явного external opt-in.
    """

    downloader = ArxivPdfDownloader(
        "https://export.arxiv.org/pdf",
        30,
        3,
        20_000_000,
        "ResearchPapersPet/0.1 (external integration test)",
    )
    try:
        downloaded = await downloader.download("1706.03762")
        assert downloaded.content.startswith(b"%PDF-")
        assert len(downloaded.checksum) == 64
    finally:
        await downloader.close()
