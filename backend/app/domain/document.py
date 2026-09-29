from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4


class DocumentSource(StrEnum):
    """
    Источник научного документа.

    Attributes:
        ARXIV (str): Автоматически получаемый arXiv PDF.
        MANUAL_UPLOAD (str): PDF, загруженный пользователем.

    Fallbacks:
        Неизвестный источник отклоняется enum-конструктором.
    """

    ARXIV = "ARXIV"
    MANUAL_UPLOAD = "MANUAL_UPLOAD"


class DocumentJobStatus(StrEnum):
    """
    Состояние независимого document processing lifecycle.

    Attributes:
        PENDING (str): Target создан и ожидает обработки.
        COMPLETED (str): Документ полностью проиндексирован.
        FAILED (str): Обработка завершилась ошибкой.

    Fallbacks:
        Переходы между состояниями проверяются can_transition_to.
    """

    PENDING = "PENDING"
    DOWNLOADING = "DOWNLOADING"
    AWAITING_UPLOAD = "AWAITING_UPLOAD"
    PARSING = "PARSING"
    CHUNKING = "CHUNKING"
    INDEXING = "INDEXING"
    COMPLETED = "COMPLETED"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"

    def can_transition_to(self, status: "DocumentJobStatus") -> bool:
        """
        Проверяет допустимость следующего состояния document job.

        Parameters:
            status (DocumentJobStatus): Запрошенное следующее состояние.

        Returns:
            bool: True для разрешённого перехода.

        Fallbacks:
            Terminal states не допускают дальнейших переходов.
        """

        # Keep every lifecycle branch explicit so skipped processing stages are rejected.
        transitions = {
            self.PENDING: {
                self.DOWNLOADING,
                self.AWAITING_UPLOAD,
                self.UNAVAILABLE,
                self.FAILED,
            },
            self.DOWNLOADING: {
                self.PARSING,
                self.AWAITING_UPLOAD,
                self.UNAVAILABLE,
                self.FAILED,
            },
            self.AWAITING_UPLOAD: {self.PARSING, self.UNAVAILABLE, self.FAILED},
            self.PARSING: {self.CHUNKING, self.FAILED},
            self.CHUNKING: {self.INDEXING, self.FAILED},
            self.INDEXING: {self.COMPLETED, self.FAILED},
            self.COMPLETED: set(),
            self.UNAVAILABLE: set(),
            self.FAILED: set(),
        }
        return status in transitions[self]


class DocumentElementType(StrEnum):
    """
    Нормализованный тип элемента parsed document.

    Attributes:
        SECTION (str): Заголовок секции.
        PARAGRAPH (str): Текстовый параграф.
        BIBLIOGRAPHY (str): Библиографическая запись.

    Fallbacks:
        Неизвестные GROBID elements будут отклонены parser layer.
    """

    SECTION = "SECTION"
    PARAGRAPH = "PARAGRAPH"
    TABLE = "TABLE"
    FIGURE_CAPTION = "FIGURE_CAPTION"
    FORMULA = "FORMULA"
    BIBLIOGRAPHY = "BIBLIOGRAPHY"


@dataclass(frozen=True, slots=True)
class StoredDocument:
    """
    Канонические metadata объекта в DocumentStorage.

    Attributes:
        key (str): Backend-independent object key.
        paper_id (UUID): Идентификатор глобальной статьи.
        document_id (UUID): Идентификатор версии документа.
        checksum (str): SHA-256 содержимого.
        media_type (str): Проверенный MIME type.
        size_bytes (int): Размер содержимого в байтах.

    Fallbacks:
        Metadata создаются только после успешной проверки PDF.
    """

    key: str
    paper_id: UUID
    document_id: UUID
    checksum: str
    media_type: str
    size_bytes: int


@dataclass(slots=True)
class PaperDocument:
    """
    Versioned PDF-артефакт глобальной статьи.

    Attributes:
        paper_id (UUID): Идентификатор глобальной Paper.
        source (DocumentSource): Источник PDF.
        version (int): Монотонная версия документа. По умолчанию: 1.

    Fallbacks:
        Storage metadata остаются None до успешного получения файла.
    """

    paper_id: UUID
    source: DocumentSource
    status: DocumentJobStatus = DocumentJobStatus.PENDING
    version: int = 1
    storage_key: str | None = None
    checksum: str | None = None
    media_type: str | None = None
    size_bytes: int | None = None
    is_active: bool = True
    created_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class DocumentProcessingJob:
    """
    Project-scoped lifecycle загрузки и обработки PDF.

    Attributes:
        project_id (UUID): Проект, запросивший PDF target.
        paper_id (UUID): Глобальная Paper target.
        status (DocumentJobStatus): Текущее состояние обработки.

    Fallbacks:
        document_id остаётся None до создания versioned PaperDocument.
    """

    project_id: UUID
    paper_id: UUID
    source: DocumentSource
    status: DocumentJobStatus = DocumentJobStatus.PENDING
    research_job_id: UUID | None = None
    document_id: UUID | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class ParsedDocument:
    """
    Versioned результат GROBID parsing.

    Attributes:
        document_id (UUID): Исходный PaperDocument.
        parser_name (str): Имя parser implementation.
        parser_version (str): Версия parser image/config.

    Fallbacks:
        TEI key и finished_at остаются None при ошибке parsing.
    """

    document_id: UUID
    parser_name: str
    parser_version: str
    tei_storage_key: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class DocumentElement:
    """
    Упорядоченный структурный элемент parsed document.

    Attributes:
        parsed_document_id (UUID): Версия parsed document.
        element_type (DocumentElementType): Нормализованный тип элемента.
        position (int): Позиция в каноническом порядке документа.

    Fallbacks:
        Section, page и coordinates остаются None при отсутствии в TEI.
    """

    parsed_document_id: UUID
    element_type: DocumentElementType
    position: int
    text: str
    section_path: list[str] | None = None
    page_number: int | None = None
    coordinates: dict | None = None
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class CitationMarker:
    """
    Связь внутритекстового marker с bibliography element.

    Attributes:
        marker_element_id (UUID): Элемент с citation marker.
        bibliography_element_id (UUID): Связанная bibliography запись.
        marker_text (str): Исходный текст marker.

    Fallbacks:
        Marker без разрешённой bibliography связи не сохраняется.
    """

    marker_element_id: UUID
    bibliography_element_id: UUID
    marker_text: str
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class PaperChunk:
    """
    Versioned token-based chunk parsed document.

    Attributes:
        parsed_document_id (UUID): Версия parsed document.
        stable_id (str): Детерминированный внешний ID chunk.
        chunk_index (int): Позиция chunk внутри набора.

    Fallbacks:
        Element, section, page и coordinates остаются None при отсутствии metadata.
    """

    parsed_document_id: UUID
    stable_id: str
    chunk_index: int
    text: str
    token_start: int
    token_end: int
    chunker_version: str
    embedding_model: str
    embedding_version: str
    element_id: UUID | None = None
    section_path: list[str] | None = None
    page_number: int | None = None
    coordinates: dict | None = None
    is_active: bool = True
    id: UUID = field(default_factory=uuid4)
