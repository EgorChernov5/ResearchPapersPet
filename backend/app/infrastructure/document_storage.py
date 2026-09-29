import json
from abc import ABC, abstractmethod
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import Settings
from app.domain.document import StoredDocument


class DocumentStorageError(ValueError):
    """
    Базовая ошибка object storage contract.

    Attributes:
        args (tuple): Диагностические аргументы ошибки.

    Fallbacks:
        Конкретные validation errors наследуют этот тип.
    """


class DocumentSizeError(DocumentStorageError):
    """
    Ошибка превышения максимального размера документа.

    Attributes:
        args (tuple): Диагностические аргументы ошибки.

    Fallbacks:
        Объект не записывается ни в один backend.
    """


class DocumentContentError(DocumentStorageError):
    """
    Ошибка MIME type или PDF signature.

    Attributes:
        args (tuple): Диагностические аргументы ошибки.

    Fallbacks:
        Объект не записывается ни в один backend.
    """


class DocumentChecksumError(DocumentStorageError):
    """
    Ошибка несовпадения ожидаемого и вычисленного checksum.

    Attributes:
        args (tuple): Диагностические аргументы ошибки.

    Fallbacks:
        Вычисленный checksum не подменяет ожидаемое значение молча.
    """


class DocumentStorage(ABC):
    """
    Минимальный backend-independent contract хранения документов.

    Attributes:
        max_bytes (int): Максимальный допустимый размер объекта.

    Fallbacks:
        Backend errors передаются application layer без изменения lifecycle в БД.
    """

    def __init__(self, max_bytes: int) -> None:
        """
        Создаёт storage с единым validation limit.

        Parameters:
            max_bytes (int): Максимальный размер PDF в байтах.

        Returns:
            None: Метод сохраняет limit.

        Fallbacks:
            Неположительный limit отклоняется.
        """

        if max_bytes <= 0:
            raise ValueError("Document storage size limit must be positive")
        self.max_bytes = max_bytes

    def prepare(
        self,
        paper_id: UUID,
        document_id: UUID,
        content: bytes,
        media_type: str,
        expected_checksum: str | None = None,
    ) -> StoredDocument:
        """
        Проверяет PDF и формирует канонические object metadata.

        Parameters:
            paper_id (UUID): Идентификатор глобальной статьи.
            document_id (UUID): Идентификатор версии документа.
            content (bytes): Бинарное содержимое PDF.
            media_type (str): Заявленный MIME type.
            expected_checksum (str | None): Ожидаемый SHA-256. По умолчанию: None.

        Returns:
            StoredDocument: Проверенные metadata и безопасный object key.

        Fallbacks:
            Size, MIME, signature и checksum errors возникают до backend write.
        """

        # Validate cheap size and content properties before computing the canonical key.
        if len(content) > self.max_bytes:
            raise DocumentSizeError(
                f"PDF size {len(content)} exceeds configured limit {self.max_bytes}"
            )
        if media_type.lower().split(";", 1)[0].strip() != "application/pdf":
            raise DocumentContentError("Document media type must be application/pdf")
        if not content.startswith(b"%PDF-"):
            raise DocumentContentError("Document content does not have a PDF signature")
        checksum = sha256(content).hexdigest()
        if expected_checksum is not None and checksum != expected_checksum.lower():
            raise DocumentChecksumError("Document checksum does not match expected SHA-256")
        key = f"papers/{paper_id}/documents/{document_id}/{checksum}.pdf"
        return StoredDocument(key, paper_id, document_id, checksum, "application/pdf", len(content))

    @abstractmethod
    def put(
        self,
        paper_id: UUID,
        document_id: UUID,
        content: bytes,
        media_type: str,
        expected_checksum: str | None = None,
        filename: str | None = None,
    ) -> StoredDocument:
        """
        Идемпотентно сохраняет проверенный PDF.

        Parameters:
            paper_id (UUID): Идентификатор глобальной статьи.
            document_id (UUID): Идентификатор версии документа.
            content (bytes): Бинарное содержимое PDF.
            media_type (str): Заявленный MIME type.
            expected_checksum (str | None): Ожидаемый SHA-256. По умолчанию: None.
            filename (str | None): Недоверенное исходное имя. По умолчанию: None.

        Returns:
            StoredDocument: Канонические metadata объекта.

        Fallbacks:
            filename не участвует в object key.
        """

    @abstractmethod
    def get(self, key: str) -> bytes:
        """
        Читает содержимое объекта.

        Parameters:
            key (str): Канонический object key.

        Returns:
            bytes: Исходное содержимое.

        Fallbacks:
            Отсутствующий объект вызывает backend-compatible ошибку.
        """

    @abstractmethod
    def exists(self, key: str) -> bool:
        """
        Проверяет существование объекта.

        Parameters:
            key (str): Канонический object key.

        Returns:
            bool: True, если объект существует.

        Fallbacks:
            Ошибки кроме not-found передаются вызывающему коду.
        """

    @abstractmethod
    def delete(self, key: str) -> None:
        """
        Идемпотентно удаляет объект и его metadata.

        Parameters:
            key (str): Канонический object key.

        Returns:
            None: Объект отсутствует после вызова.

        Fallbacks:
            Повторное удаление разрешено.
        """

    @abstractmethod
    def get_metadata(self, key: str) -> StoredDocument:
        """
        Читает канонические metadata объекта.

        Parameters:
            key (str): Канонический object key.

        Returns:
            StoredDocument: Metadata сохранённого объекта.

        Fallbacks:
            Отсутствующий объект вызывает backend-compatible ошибку.
        """


class LocalVolumeDocumentStorage(DocumentStorage):
    """
    Хранит документы и metadata в local volume.

    Attributes:
        root (Path): Абсолютный корень object storage.
        max_bytes (int): Максимальный размер PDF.

    Fallbacks:
        Попытка выйти за root через key отклоняется.
    """

    def __init__(self, root: str | Path, max_bytes: int) -> None:
        """
        Создаёт local volume adapter.

        Parameters:
            root (str | Path): Корень хранения объектов.
            max_bytes (int): Максимальный размер PDF.

        Returns:
            None: Каталог создаётся при первом put.

        Fallbacks:
            Относительный root разрешается относительно рабочего каталога.
        """

        super().__init__(max_bytes)
        self.root = Path(root).resolve()

    def put(
        self,
        paper_id: UUID,
        document_id: UUID,
        content: bytes,
        media_type: str,
        expected_checksum: str | None = None,
        filename: str | None = None,
    ) -> StoredDocument:
        """
        Идемпотентно сохраняет PDF и JSON metadata.

        Parameters:
            paper_id (UUID): Идентификатор глобальной статьи.
            document_id (UUID): Идентификатор версии документа.
            content (bytes): Бинарное содержимое PDF.
            media_type (str): Заявленный MIME type.
            expected_checksum (str | None): Ожидаемый SHA-256. По умолчанию: None.
            filename (str | None): Недоверенное исходное имя. По умолчанию: None.

        Returns:
            StoredDocument: Канонические metadata объекта.

        Fallbacks:
            Повторный checksum возвращает существующий объект без перезаписи.
        """

        # Validate before creating directories; the filename is deliberately unused.
        metadata = self.prepare(
            paper_id,
            document_id,
            content,
            media_type,
            expected_checksum,
        )
        target = (self.root / metadata.key).resolve()
        if self.root != target and self.root not in target.parents:
            raise DocumentStorageError("Document object key escapes local storage root")
        if target.exists():
            return self.get_metadata(metadata.key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        metadata_path = target.with_suffix(f"{target.suffix}.metadata.json")
        metadata_path.write_text(
            json.dumps(
                {
                    "key": metadata.key,
                    "paper_id": str(metadata.paper_id),
                    "document_id": str(metadata.document_id),
                    "checksum": metadata.checksum,
                    "media_type": metadata.media_type,
                    "size_bytes": metadata.size_bytes,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
            newline="\n",
        )
        return metadata

    def get(self, key: str) -> bytes:
        """
        Читает PDF из local volume.

        Parameters:
            key (str): Канонический object key.

        Returns:
            bytes: Исходное содержимое PDF.

        Fallbacks:
            Path traversal и отсутствующий файл вызывают ошибку.
        """

        # Resolve every caller-provided key inside the configured root.
        target = (self.root / key).resolve()
        if self.root != target and self.root not in target.parents:
            raise DocumentStorageError("Document object key escapes local storage root")
        return target.read_bytes()

    def exists(self, key: str) -> bool:
        """
        Проверяет PDF в local volume.

        Parameters:
            key (str): Канонический object key.

        Returns:
            bool: True для существующего файла.

        Fallbacks:
            Path traversal отклоняется.
        """

        # Never inspect paths outside the configured root.
        target = (self.root / key).resolve()
        if self.root != target and self.root not in target.parents:
            raise DocumentStorageError("Document object key escapes local storage root")
        return target.is_file()

    def delete(self, key: str) -> None:
        """
        Удаляет local PDF и JSON metadata.

        Parameters:
            key (str): Канонический object key.

        Returns:
            None: Оба файла отсутствуют после вызова.

        Fallbacks:
            Отсутствующие файлы не считаются ошибкой.
        """

        # Remove only the exact object pair without recursive directory operations.
        target = (self.root / key).resolve()
        if self.root != target and self.root not in target.parents:
            raise DocumentStorageError("Document object key escapes local storage root")
        metadata_path = target.with_suffix(f"{target.suffix}.metadata.json")
        target.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)

    def get_metadata(self, key: str) -> StoredDocument:
        """
        Читает JSON metadata local объекта.

        Parameters:
            key (str): Канонический object key.

        Returns:
            StoredDocument: Десериализованные metadata.

        Fallbacks:
            Missing или повреждённый metadata file вызывает ошибку чтения.
        """

        # Keep object metadata adjacent to its immutable checksum-addressed PDF.
        target = (self.root / key).resolve()
        if self.root != target and self.root not in target.parents:
            raise DocumentStorageError("Document object key escapes local storage root")
        values = json.loads(
            target.with_suffix(f"{target.suffix}.metadata.json").read_text(encoding="utf-8")
        )
        return StoredDocument(
            values["key"],
            UUID(values["paper_id"]),
            UUID(values["document_id"]),
            values["checksum"],
            values["media_type"],
            values["size_bytes"],
        )


class S3DocumentStorage(DocumentStorage):
    """
    Хранит документы в AWS S3-compatible backend.

    Attributes:
        bucket (str): Имя bucket.
        client (S3Client): Boto3 S3 client.

    Fallbacks:
        Endpoint можно направить на RustFS или другой S3-compatible service без изменения contract.
    """

    def __init__(
        self,
        bucket: str,
        max_bytes: int,
        endpoint_url: str | None = None,
        region: str = "us-east-1",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ) -> None:
        """
        Создаёт S3-compatible adapter без сетевого запроса.

        Parameters:
            bucket (str): Имя существующего bucket.
            max_bytes (int): Максимальный размер PDF.
            endpoint_url (str | None): Custom S3 endpoint. По умолчанию: None.
            region (str): AWS region. По умолчанию: us-east-1.
            access_key_id (str | None): Static access key. По умолчанию: None.
            secret_access_key (str | None): Static secret key. По умолчанию: None.

        Returns:
            None: Клиент подключится при первой операции.

        Fallbacks:
            Без static credentials используется стандартная AWS credential chain.
        """

        super().__init__(max_bytes)
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(s3={"addressing_style": "path"}),
        )

    def put(
        self,
        paper_id: UUID,
        document_id: UUID,
        content: bytes,
        media_type: str,
        expected_checksum: str | None = None,
        filename: str | None = None,
    ) -> StoredDocument:
        """
        Идемпотентно сохраняет PDF в S3-compatible bucket.

        Parameters:
            paper_id (UUID): Идентификатор глобальной статьи.
            document_id (UUID): Идентификатор версии документа.
            content (bytes): Бинарное содержимое PDF.
            media_type (str): Заявленный MIME type.
            expected_checksum (str | None): Ожидаемый SHA-256. По умолчанию: None.
            filename (str | None): Недоверенное исходное имя. По умолчанию: None.

        Returns:
            StoredDocument: Канонические metadata объекта.

        Fallbacks:
            Повторный checksum возвращает HEAD metadata без перезаписи.
        """

        # Validate the complete object before the first remote request.
        metadata = self.prepare(
            paper_id,
            document_id,
            content,
            media_type,
            expected_checksum,
        )
        if self.exists(metadata.key):
            return self.get_metadata(metadata.key)
        self.client.put_object(
            Bucket=self.bucket,
            Key=metadata.key,
            Body=content,
            ContentType=metadata.media_type,
            Metadata={
                "paper-id": str(metadata.paper_id),
                "document-id": str(metadata.document_id),
                "checksum": metadata.checksum,
            },
        )
        return metadata

    def get(self, key: str) -> bytes:
        """
        Читает PDF из S3-compatible bucket.

        Parameters:
            key (str): Канонический object key.

        Returns:
            bytes: Исходное содержимое PDF.

        Fallbacks:
            S3 errors передаются вызывающему коду.
        """

        # Consume the response body inside this synchronous storage boundary.
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        """
        Проверяет объект через S3 HEAD.

        Parameters:
            key (str): Канонический object key.

        Returns:
            bool: False только для not-found ответа.

        Fallbacks:
            Permission и service errors не маскируются как отсутствие объекта.
        """

        # Distinguish an absent key from operational S3 failures.
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True

    def delete(self, key: str) -> None:
        """
        Идемпотентно удаляет S3 object.

        Parameters:
            key (str): Канонический object key.

        Returns:
            None: S3 принимает удаление отсутствующего key.

        Fallbacks:
            Service errors передаются вызывающему коду.
        """

        # Object metadata are removed atomically with the S3 object.
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def get_metadata(self, key: str) -> StoredDocument:
        """
        Читает S3 HEAD metadata.

        Parameters:
            key (str): Канонический object key.

        Returns:
            StoredDocument: Канонические metadata объекта.

        Fallbacks:
            Missing required metadata вызывает KeyError/ValueError.
        """

        # Hydrate the same DTO returned by the local backend.
        response = self.client.head_object(Bucket=self.bucket, Key=key)
        metadata = response["Metadata"]
        return StoredDocument(
            key,
            UUID(metadata["paper-id"]),
            UUID(metadata["document-id"]),
            metadata["checksum"],
            response["ContentType"].split(";", 1)[0],
            response["ContentLength"],
        )


def create_document_storage(config: Settings) -> DocumentStorage:
    """
    Создаёт ровно один adapter из application settings.

    Parameters:
        config (Settings): Проверенная конфигурация приложения.

    Returns:
        DocumentStorage: Local или S3-compatible backend.

    Fallbacks:
        Settings отклоняет неизвестное имя backend до вызова factory.
    """

    # Keep backend selection in one composition boundary for API and workers.
    if config.document_storage_backend == "local":
        return LocalVolumeDocumentStorage(
            config.document_storage_local_root,
            config.document_storage_max_bytes,
        )
    return S3DocumentStorage(
        config.document_storage_s3_bucket,
        config.document_storage_max_bytes,
        config.document_storage_s3_endpoint_url or None,
        config.document_storage_s3_region,
        config.document_storage_s3_access_key_id or None,
        config.document_storage_s3_secret_access_key or None,
    )
