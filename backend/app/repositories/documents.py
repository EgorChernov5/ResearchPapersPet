from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.document import (
    CitationMarker,
    DocumentElement,
    DocumentJobStatus,
    DocumentProcessingJob,
    DocumentSource,
    PaperChunk,
    PaperDocument,
    ParsedDocument,
)
from app.infrastructure.models import (
    CitationMarkerModel,
    DocumentElementModel,
    DocumentProcessingJobModel,
    PaperChunkModel,
    PaperDocumentModel,
    ParsedDocumentModel,
)


class DocumentJobRepository:
    """
    Управляет project-scoped PDF targets и их lifecycle.

    Attributes:
        session (Session): Текущая SQLAlchemy transaction session.

    Fallbacks:
        Повторное создание target возвращает существующую job.
    """

    def __init__(self, session: Session) -> None:
        """
        Создаёт repository внутри внешней transaction boundary.

        Parameters:
            session (Session): SQLAlchemy session.

        Returns:
            None: Метод сохраняет session.

        Fallbacks:
            Commit и rollback выполняет application layer.
        """

        self.session = session

    def create_target(
        self,
        project_id: UUID,
        paper_id: UUID,
        research_job_id: UUID,
        source: DocumentSource = DocumentSource.ARXIV,
    ) -> DocumentProcessingJob:
        """
        Идемпотентно создаёт PDF target в PENDING.

        Parameters:
            project_id (UUID): Проект-владелец target.
            paper_id (UUID): Global Paper target.
            research_job_id (UUID): ResearchJob, выбравший target.
            source (DocumentSource): Планируемый источник. По умолчанию: ARXIV.

        Returns:
            DocumentProcessingJob: Новая или существующая target job.

        Fallbacks:
            Database foreign keys отклоняют неизвестные parent entities.
        """

        # Reuse the project/paper/source target across repeated research jobs.
        model = self.session.scalar(
            select(DocumentProcessingJobModel).where(
                DocumentProcessingJobModel.project_id == project_id,
                DocumentProcessingJobModel.paper_id == paper_id,
                DocumentProcessingJobModel.source == source.value,
            )
        )
        if model is None:
            model = DocumentProcessingJobModel(
                project_id=project_id,
                paper_id=paper_id,
                research_job_id=research_job_id,
                source=source.value,
                status=DocumentJobStatus.PENDING.value,
            )
            self.session.add(model)
            self.session.flush()
        return self._to_domain(model)

    def get_for_project(self, project_id: UUID) -> list[DocumentProcessingJob]:
        """
        Возвращает document jobs проекта в стабильном порядке.

        Parameters:
            project_id (UUID): Идентификатор проекта.

        Returns:
            list[DocumentProcessingJob]: Persisted jobs по paper ID.

        Fallbacks:
            Проект без targets возвращает пустой список.
        """

        # Stable ordering keeps status diagnostics and tests deterministic.
        models = self.session.scalars(
            select(DocumentProcessingJobModel)
            .where(DocumentProcessingJobModel.project_id == project_id)
            .order_by(DocumentProcessingJobModel.paper_id)
        )
        return [self._to_domain(model) for model in models]

    def get(self, job_id: UUID) -> DocumentProcessingJob | None:
        """
        Возвращает document job по идентификатору.

        Parameters:
            job_id (UUID): Идентификатор target job.

        Returns:
            DocumentProcessingJob | None: Найденная job или None.

        Fallbacks:
            Missing row не создаёт exception.
        """

        # Keep authorization checks in application services using the hydrated project ID.
        model = self.session.get(DocumentProcessingJobModel, job_id)
        return self._to_domain(model) if model is not None else None

    def get_target(
        self,
        project_id: UUID,
        paper_id: UUID,
    ) -> DocumentProcessingJob | None:
        """
        Возвращает target конкретной статьи внутри проекта.

        Parameters:
            project_id (UUID): Идентификатор проекта-владельца.
            paper_id (UUID): Идентификатор разрешённой статьи.

        Returns:
            DocumentProcessingJob | None: Target или None.

        Fallbacks:
            Target другого проекта не раскрывается.
        """

        # Manual upload authorization is scoped by both route identifiers.
        model = self.session.scalar(
            select(DocumentProcessingJobModel).where(
                DocumentProcessingJobModel.project_id == project_id,
                DocumentProcessingJobModel.paper_id == paper_id,
            )
        )
        return self._to_domain(model) if model is not None else None

    def update_status(
        self,
        job_id: UUID,
        status: DocumentJobStatus,
        document_id: UUID | None = None,
        error_message: str | None = None,
    ) -> DocumentProcessingJob:
        """
        Выполняет один допустимый lifecycle transition.

        Parameters:
            job_id (UUID): Идентификатор document job.
            status (DocumentJobStatus): Следующее состояние.
            document_id (UUID | None): Созданная версия PDF. По умолчанию: None.
            error_message (str | None): Failure diagnostics. По умолчанию: None.

        Returns:
            DocumentProcessingJob: Обновлённое состояние.

        Fallbacks:
            Missing job и невозможный переход вызывают ValueError.
        """

        model = self.session.get(DocumentProcessingJobModel, job_id)
        if model is None:
            raise ValueError(f"Document processing job {job_id} was not found")
        current = DocumentJobStatus(model.status)
        if not current.can_transition_to(status):
            raise ValueError(f"Invalid document job transition: {current.value} -> {status.value}")

        # Persist timestamps at the first active stage and every terminal outcome.
        model.status = status.value
        if model.started_at is None and status != DocumentJobStatus.PENDING:
            model.started_at = datetime.now(UTC)
        if status in {
            DocumentJobStatus.COMPLETED,
            DocumentJobStatus.UNAVAILABLE,
            DocumentJobStatus.FAILED,
        }:
            model.finished_at = datetime.now(UTC)
        if document_id is not None:
            model.document_id = document_id
        model.error_message = error_message
        self.session.flush()
        return self._to_domain(model)

    def _to_domain(self, model: DocumentProcessingJobModel) -> DocumentProcessingJob:
        """
        Преобразует ORM row в domain entity.

        Parameters:
            model (DocumentProcessingJobModel): Persistence model.

        Returns:
            DocumentProcessingJob: Framework-independent entity.

        Fallbacks:
            Invalid persisted enum value вызывает ValueError.
        """

        return DocumentProcessingJob(
            id=model.id,
            project_id=model.project_id,
            paper_id=model.paper_id,
            research_job_id=model.research_job_id,
            document_id=model.document_id,
            source=DocumentSource(model.source),
            status=DocumentJobStatus(model.status),
            error_message=model.error_message,
            started_at=model.started_at,
            finished_at=model.finished_at,
            created_at=model.created_at,
        )


class DocumentRepository:
    """
    Сохраняет versioned PDF, parser, element и chunk records.

    Attributes:
        session (Session): Текущая SQLAlchemy transaction session.

    Fallbacks:
        Unique constraints защищают versioned contracts от duplicates.
    """

    def __init__(self, session: Session) -> None:
        """
        Создаёт repository внутри внешней transaction boundary.

        Parameters:
            session (Session): SQLAlchemy session.

        Returns:
            None: Метод сохраняет session.

        Fallbacks:
            Commit и rollback выполняет application layer.
        """

        self.session = session

    def create_document(
        self,
        paper_id: UUID,
        source: DocumentSource,
        storage_key: str,
        checksum: str,
        media_type: str,
        size_bytes: int,
        document_id: UUID | None = None,
    ) -> PaperDocument:
        """
        Создаёт новую active PDF version или возвращает совпавшую по checksum.

        Parameters:
            paper_id (UUID): Идентификатор global Paper.
            source (DocumentSource): Источник PDF.
            storage_key (str): Object storage key.
            checksum (str): Content checksum.
            media_type (str): Проверенный MIME type.
            size_bytes (int): Размер PDF в байтах.
            document_id (UUID | None): ID, использованный в storage key. По умолчанию: None.

        Returns:
            PaperDocument: Active version PDF.

        Fallbacks:
            Отрицательный размер отклоняется до database constraint.
        """

        if size_bytes < 0:
            raise ValueError("Document size must be non-negative")
        current = self.session.scalar(
            select(PaperDocumentModel).where(
                PaperDocumentModel.paper_id == paper_id,
                PaperDocumentModel.source == source.value,
                PaperDocumentModel.is_active.is_(True),
            )
        )
        if current is not None and current.checksum == checksum:
            return self._document_to_domain(current)

        # Retire the previous active artifact before inserting its successor.
        if current is not None:
            current.is_active = False
        version = self.session.scalar(
            select(func.max(PaperDocumentModel.version)).where(
                PaperDocumentModel.paper_id == paper_id,
                PaperDocumentModel.source == source.value,
            )
        )
        model = PaperDocumentModel(
            id=document_id or uuid4(),
            paper_id=paper_id,
            source=source.value,
            version=(version or 0) + 1,
            storage_key=storage_key,
            checksum=checksum,
            media_type=media_type,
            size_bytes=size_bytes,
            status=DocumentJobStatus.PARSING.value,
            is_active=True,
        )
        self.session.add(model)
        self.session.flush()
        return self._document_to_domain(model)

    def get_active_document(
        self,
        paper_id: UUID,
        source: DocumentSource,
    ) -> PaperDocument | None:
        """
        Возвращает active document для paper/source.

        Parameters:
            paper_id (UUID): Идентификатор global Paper.
            source (DocumentSource): Источник документа.

        Returns:
            PaperDocument | None: Активная версия или None.

        Fallbacks:
            Отсутствующая версия не создаёт placeholder row.
        """

        # Resolve idempotency before writing another immutable storage object.
        model = self.session.scalar(
            select(PaperDocumentModel).where(
                PaperDocumentModel.paper_id == paper_id,
                PaperDocumentModel.source == source.value,
                PaperDocumentModel.is_active.is_(True),
            )
        )
        return self._document_to_domain(model) if model is not None else None

    def create_parsed_document(
        self,
        document_id: UUID,
        parser_name: str,
        parser_version: str,
        tei_storage_key: str | None = None,
    ) -> ParsedDocument:
        """
        Идемпотентно создаёт parser version для PDF.

        Parameters:
            document_id (UUID): Идентификатор PaperDocument.
            parser_name (str): Имя parser.
            parser_version (str): Версия parser/config.
            tei_storage_key (str | None): Object key исходного TEI. По умолчанию: None.

        Returns:
            ParsedDocument: Persisted parser result.

        Fallbacks:
            Повторный вызов возвращает существующую версию.
        """

        model = self.session.scalar(
            select(ParsedDocumentModel).where(
                ParsedDocumentModel.document_id == document_id,
                ParsedDocumentModel.parser_name == parser_name,
                ParsedDocumentModel.parser_version == parser_version,
            )
        )
        if model is None:
            model = ParsedDocumentModel(
                document_id=document_id,
                parser_name=parser_name,
                parser_version=parser_version,
                tei_storage_key=tei_storage_key,
            )
            self.session.add(model)
            self.session.flush()
        return ParsedDocument(
            id=model.id,
            document_id=model.document_id,
            parser_name=model.parser_name,
            parser_version=model.parser_version,
            tei_storage_key=model.tei_storage_key,
            error_message=model.error_message,
            created_at=model.created_at,
            finished_at=model.finished_at,
        )

    def add_element(self, element: DocumentElement) -> DocumentElement:
        """
        Сохраняет один нормализованный document element.

        Parameters:
            element (DocumentElement): Канонический элемент.

        Returns:
            DocumentElement: Исходная domain entity.

        Fallbacks:
            Duplicate position отклоняется database constraint.
        """

        # Persist structural metadata without interpreting parser-specific coordinates.
        self.session.add(
            DocumentElementModel(
                id=element.id,
                parsed_document_id=element.parsed_document_id,
                element_type=element.element_type.value,
                position=element.position,
                text=element.text,
                section_path=element.section_path,
                page_number=element.page_number,
                coordinates=element.coordinates,
            )
        )
        self.session.flush()
        return element

    def add_citation_marker(self, marker: CitationMarker) -> CitationMarker:
        """
        Сохраняет marker → bibliography relation.

        Parameters:
            marker (CitationMarker): Разрешённая citation relation.

        Returns:
            CitationMarker: Исходная domain entity.

        Fallbacks:
            Missing elements и duplicate relation отклоняются constraints.
        """

        # Keep the original marker text next to canonical element identifiers.
        self.session.add(
            CitationMarkerModel(
                id=marker.id,
                marker_element_id=marker.marker_element_id,
                bibliography_element_id=marker.bibliography_element_id,
                marker_text=marker.marker_text,
            )
        )
        self.session.flush()
        return marker

    def add_chunk(self, chunk: PaperChunk) -> PaperChunk:
        """
        Сохраняет canonical versioned paper chunk.

        Parameters:
            chunk (PaperChunk): Chunk text, offsets и version metadata.

        Returns:
            PaperChunk: Исходная domain entity.

        Fallbacks:
            Duplicate stable ID, version position или active position отклоняются constraints.
        """

        # PostgreSQL remains the source of truth for later Qdrant indexing.
        self.session.add(
            PaperChunkModel(
                id=chunk.id,
                parsed_document_id=chunk.parsed_document_id,
                element_id=chunk.element_id,
                stable_id=chunk.stable_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                token_start=chunk.token_start,
                token_end=chunk.token_end,
                section_path=chunk.section_path,
                page_number=chunk.page_number,
                coordinates=chunk.coordinates,
                chunker_version=chunk.chunker_version,
                embedding_model=chunk.embedding_model,
                embedding_version=chunk.embedding_version,
                is_active=chunk.is_active,
            )
        )
        self.session.flush()
        return chunk

    def _document_to_domain(self, model: PaperDocumentModel) -> PaperDocument:
        """
        Преобразует PDF ORM row в domain entity.

        Parameters:
            model (PaperDocumentModel): Persistence model.

        Returns:
            PaperDocument: Framework-independent PDF version.

        Fallbacks:
            Invalid enum value вызывает ValueError.
        """

        return PaperDocument(
            id=model.id,
            paper_id=model.paper_id,
            source=DocumentSource(model.source),
            version=model.version,
            storage_key=model.storage_key,
            checksum=model.checksum,
            media_type=model.media_type,
            size_bytes=model.size_bytes,
            status=DocumentJobStatus(model.status),
            is_active=model.is_active,
            created_at=model.created_at,
        )
