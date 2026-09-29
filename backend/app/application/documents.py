from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy.orm import sessionmaker

from app.application.exceptions import ResourceNotFoundError
from app.domain.document import DocumentJobStatus, DocumentProcessingJob, DocumentSource
from app.infrastructure.document_storage import DocumentStorage
from app.providers.arxiv import (
    ArxivDocumentUnavailableError,
    ArxivPdfDownloader,
)
from app.repositories.documents import DocumentJobRepository, DocumentRepository
from app.repositories.papers import PaperRepository
from app.repositories.projects import ProjectRepository


class GetProjectDocuments:
    """
    Читает project-scoped document lifecycle.

    Attributes:
        session_factory (sessionmaker): Фабрика database sessions.

    Fallbacks:
        Missing project вызывает ResourceNotFoundError.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        """
        Создаёт read use case.

        Parameters:
            session_factory (sessionmaker): Фабрика database sessions.

        Returns:
            None: Метод сохраняет dependency.

        Fallbacks:
            Database errors передаются API boundary.
        """

        self.session_factory = session_factory

    def execute(self, project_id: UUID) -> list[DocumentProcessingJob]:
        """
        Возвращает document jobs проекта.

        Parameters:
            project_id (UUID): Идентификатор проекта.

        Returns:
            list[DocumentProcessingJob]: Jobs в стабильном порядке.

        Fallbacks:
            Missing project вызывает ResourceNotFoundError.
        """

        # Verify the owning project before returning its target list.
        with self.session_factory() as session:
            if ProjectRepository(session).get_config(project_id) is None:
                raise ResourceNotFoundError(f"Research project {project_id} was not found")
            return DocumentJobRepository(session).get_for_project(project_id)


class ProcessProjectDocuments:
    """
    Обрабатывает pending automatic arXiv targets независимо от ResearchJob.

    Attributes:
        session_factory (sessionmaker): Фабрика database sessions.
        storage (DocumentStorage): Активный object storage.
        downloader (ArxivPdfDownloader): Проверяющий HTTP downloader.

    Fallbacks:
        Ошибка одного target сохраняется в его lifecycle и не останавливает остальные.
    """

    def __init__(
        self,
        session_factory: sessionmaker,
        storage: DocumentStorage,
        downloader: ArxivPdfDownloader,
    ) -> None:
        """
        Создаёт automatic document processor.

        Parameters:
            session_factory (sessionmaker): Фабрика database sessions.
            storage (DocumentStorage): Активный object storage.
            downloader (ArxivPdfDownloader): arXiv client.

        Returns:
            None: Метод сохраняет dependencies.

        Fallbacks:
            Lifecycle persistence выполняется отдельно для каждого target.
        """

        self.session_factory = session_factory
        self.storage = storage
        self.downloader = downloader

    async def execute(self, project_id: UUID) -> list[DocumentProcessingJob]:
        """
        Загружает все новые automatic targets проекта.

        Parameters:
            project_id (UUID): Идентификатор проекта.

        Returns:
            list[DocumentProcessingJob]: Итоговые persisted states.

        Fallbacks:
            Missing/invalid PDF использует project manual-upload policy.
        """

        # Snapshot only PENDING targets; parsing and terminal jobs remain idempotently untouched.
        with self.session_factory() as session:
            config = ProjectRepository(session).get_config(project_id)
            if config is None:
                raise ResourceNotFoundError(f"Research project {project_id} was not found")
            target_ids = [
                job.id
                for job in DocumentJobRepository(session).get_for_project(project_id)
                if job.status == DocumentJobStatus.PENDING
            ]

        # Isolate a transaction per document so unavailable papers never roll back siblings.
        for job_id in target_ids:
            with self.session_factory() as session:
                jobs = DocumentJobRepository(session)
                job = jobs.get(job_id)
                if job is None or job.status != DocumentJobStatus.PENDING:
                    continue
                arxiv_id = PaperRepository(session).get_external_identifier(job.paper_id, "arxiv")
                if arxiv_id is None:
                    status = (
                        DocumentJobStatus.AWAITING_UPLOAD
                        if config.allow_manual_pdf_upload
                        else DocumentJobStatus.UNAVAILABLE
                    )
                    jobs.update_status(
                        job.id,
                        status,
                        error_message="Canonical arXiv ID is missing",
                    )
                    session.commit()
                    continue
                jobs.update_status(job.id, DocumentJobStatus.DOWNLOADING)
                session.commit()

            try:
                downloaded = await self.downloader.download(arxiv_id)
                with self.session_factory() as session:
                    jobs = DocumentJobRepository(session)
                    job = jobs.get(job_id)
                    documents = DocumentRepository(session)
                    active = documents.get_active_document(job.paper_id, DocumentSource.ARXIV)
                    if active is not None and active.checksum == downloaded.checksum:
                        document = active
                    else:
                        document_id = uuid4()
                        stored = self.storage.put(
                            job.paper_id,
                            document_id,
                            downloaded.content,
                            downloaded.media_type,
                            downloaded.checksum,
                        )
                        document = documents.create_document(
                            job.paper_id,
                            DocumentSource.ARXIV,
                            stored.key,
                            stored.checksum,
                            stored.media_type,
                            stored.size_bytes,
                            document_id,
                        )
                    jobs.update_status(job.id, DocumentJobStatus.PARSING, document.id)
                    session.commit()
            except ArxivDocumentUnavailableError as error:
                with self.session_factory() as session:
                    status = (
                        DocumentJobStatus.AWAITING_UPLOAD
                        if config.allow_manual_pdf_upload
                        else DocumentJobStatus.UNAVAILABLE
                    )
                    DocumentJobRepository(session).update_status(
                        job_id,
                        status,
                        error_message=str(error),
                    )
                    session.commit()
            except Exception as error:
                with self.session_factory() as session:
                    DocumentJobRepository(session).update_status(
                        job_id,
                        DocumentJobStatus.FAILED,
                        error_message=str(error),
                    )
                    session.commit()

        # Return current states for worker diagnostics and direct integration usage.
        return GetProjectDocuments(self.session_factory).execute(project_id)


class UploadPaperDocument:
    """
    Сохраняет разрешённый manual PDF и переводит target к parsing.

    Attributes:
        session_factory (sessionmaker): Фабрика database sessions.
        storage (DocumentStorage): Активный object storage.

    Fallbacks:
        Upload разрешён только для AWAITING_UPLOAD target с включённым project flag.
    """

    def __init__(self, session_factory: sessionmaker, storage: DocumentStorage) -> None:
        """
        Создаёт manual upload use case.

        Parameters:
            session_factory (sessionmaker): Фабрика database sessions.
            storage (DocumentStorage): Активный object storage.

        Returns:
            None: Метод сохраняет dependencies.

        Fallbacks:
            Storage validation errors передаются API boundary.
        """

        self.session_factory = session_factory
        self.storage = storage

    def execute(
        self,
        project_id: UUID,
        paper_id: UUID,
        content: bytes,
        media_type: str,
        filename: str,
    ) -> DocumentProcessingJob:
        """
        Проверяет permission, сохраняет новую version и обновляет lifecycle.

        Parameters:
            project_id (UUID): Идентификатор проекта.
            paper_id (UUID): Идентификатор разрешённого target paper.
            content (bytes): Multipart file bytes.
            media_type (str): Заявленный upload MIME type.
            filename (str): Недоверенное имя upload.

        Returns:
            DocumentProcessingJob: Job в статусе PARSING.

        Fallbacks:
            Missing target даёт 404 application error, disabled/wrong state — ValueError.
        """

        # Authorize against the persisted project config and exact project/paper target.
        with self.session_factory() as session:
            config = ProjectRepository(session).get_config(project_id)
            if config is None:
                raise ResourceNotFoundError(f"Research project {project_id} was not found")
            job = DocumentJobRepository(session).get_target(project_id, paper_id)
            if job is None:
                raise ResourceNotFoundError(
                    f"Document target for paper {paper_id} in project {project_id} was not found"
                )
            if not config.allow_manual_pdf_upload:
                raise ValueError("Manual PDF upload is disabled for this project")
            if job.status != DocumentJobStatus.AWAITING_UPLOAD:
                raise ValueError("Document target is not awaiting a manual upload")

            # Validate and persist the immutable object before exposing the document version.
            document_id = uuid4()
            checksum = sha256(content).hexdigest()
            stored = self.storage.put(
                paper_id,
                document_id,
                content,
                media_type,
                checksum,
                filename,
            )
            document = DocumentRepository(session).create_document(
                paper_id,
                DocumentSource.MANUAL_UPLOAD,
                stored.key,
                stored.checksum,
                stored.media_type,
                stored.size_bytes,
                document_id,
            )
            updated = DocumentJobRepository(session).update_status(
                job.id,
                DocumentJobStatus.PARSING,
                document.id,
            )
            session.commit()
            return updated
