from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import boto3
import pytest
from app.config import Settings
from app.infrastructure.document_storage import (
    DocumentChecksumError,
    DocumentContentError,
    DocumentSizeError,
    LocalVolumeDocumentStorage,
    S3DocumentStorage,
    create_document_storage,
)
from botocore.config import Config
from botocore.exceptions import ClientError


@pytest.mark.parametrize(
    "backend",
    [
        "local",
        pytest.param("s3", marks=pytest.mark.service_integration),
    ],
)
def test_document_storage_contract(backend: str, tmp_path: Path) -> None:
    """
    Проверяет единый write/read/metadata/delete contract local и RustFS backends.

    Parameters:
        backend (str): Имя проверяемого backend.
        tmp_path (Path): Изолированный каталог pytest.

    Returns:
        None: Assertions подтверждают одинаковое поведение adapters.

    Fallbacks:
        RustFS parameter запускается только в service_integration profile.
    """

    # Build the requested real backend without replacing its storage operations.
    config = Settings(
        document_storage_backend=backend,
        document_storage_local_root=str(tmp_path),
        document_storage_s3_endpoint_url="http://127.0.0.1:59000",
        document_storage_s3_bucket="research-documents",
        document_storage_s3_access_key_id="research",
        document_storage_s3_secret_access_key="research-secret",
    )
    if backend == "s3":
        client = boto3.client(
            "s3",
            endpoint_url=config.document_storage_s3_endpoint_url,
            region_name=config.document_storage_s3_region,
            aws_access_key_id=config.document_storage_s3_access_key_id,
            aws_secret_access_key=config.document_storage_s3_secret_access_key,
            config=Config(s3={"addressing_style": "path"}),
        )
        try:
            client.create_bucket(Bucket=config.document_storage_s3_bucket)
        except ClientError as error:
            if error.response["Error"]["Code"] not in {
                "BucketAlreadyExists",
                "BucketAlreadyOwnedByYou",
            }:
                raise
    storage = create_document_storage(config)
    paper_id = uuid4()
    document_id = uuid4()
    content = b"%PDF-1.7\ncontract fixture\n%%EOF"

    # Exercise the complete contract and verify user filenames cannot affect the object key.
    stored = storage.put(
        paper_id,
        document_id,
        content,
        "application/pdf",
        sha256(content).hexdigest(),
        "../../outside.pdf",
    )
    repeated = storage.put(
        paper_id,
        document_id,
        content,
        "application/pdf",
        sha256(content).hexdigest(),
        "another-name.pdf",
    )
    assert stored == repeated
    assert "outside" not in stored.key
    assert "another-name" not in stored.key
    assert stored.key == (
        f"papers/{paper_id}/documents/{document_id}/{sha256(content).hexdigest()}.pdf"
    )
    assert storage.exists(stored.key)
    assert storage.get(stored.key) == content
    assert storage.get_metadata(stored.key) == stored
    storage.delete(stored.key)
    assert not storage.exists(stored.key)


def test_local_storage_creates_new_key_for_changed_checksum(tmp_path: Path) -> None:
    """
    Проверяет разделение document versions по checksum.

    Parameters:
        tmp_path (Path): Изолированный local storage root.

    Returns:
        None: Разное содержимое получает разные object keys.

    Fallbacks:
        Оба объекта остаются доступными до явного удаления.
    """

    # Store two physical versions under the same paper and document identifiers.
    storage = LocalVolumeDocumentStorage(tmp_path, 1_000)
    paper_id = uuid4()
    document_id = uuid4()
    first = storage.put(paper_id, document_id, b"%PDF-1.4\nfirst", "application/pdf")
    second = storage.put(paper_id, document_id, b"%PDF-1.4\nsecond", "application/pdf")
    assert first.key != second.key
    assert storage.exists(first.key)
    assert storage.exists(second.key)


@pytest.mark.parametrize(
    ("content", "media_type", "error"),
    [
        (b"%PDF-1.4\nlarge", "application/pdf", DocumentSizeError),
        (b"<html>", "text/html", DocumentContentError),
        (b"not-pdf", "application/pdf", DocumentContentError),
    ],
)
def test_local_storage_rejects_invalid_content_before_write(
    tmp_path: Path,
    content: bytes,
    media_type: str,
    error: type[ValueError],
) -> None:
    """
    Проверяет validation boundary до успешной записи объекта.

    Parameters:
        tmp_path (Path): Изолированный local storage root.
        content (bytes): Проверяемое содержимое.
        media_type (str): Заявленный MIME type.
        error (type[ValueError]): Ожидаемая ошибка validation.

    Returns:
        None: Невалидный объект отсутствует в storage.

    Fallbacks:
        Size и PDF content проверяются до создания object metadata.
    """

    # Use a deliberately small limit for the oversized contract case.
    storage = LocalVolumeDocumentStorage(tmp_path, 12)
    paper_id = uuid4()
    document_id = uuid4()
    checksum = sha256(content).hexdigest()
    expected_key = f"papers/{paper_id}/documents/{document_id}/{checksum}.pdf"
    with pytest.raises(error):
        storage.put(paper_id, document_id, content, media_type)
    assert not storage.exists(expected_key)


def test_local_storage_rejects_mismatched_checksum_before_write(tmp_path: Path) -> None:
    """
    Проверяет expected checksum до сохранения объекта.

    Parameters:
        tmp_path (Path): Изолированный local storage root.

    Returns:
        None: Объект с неверным checksum не записывается.

    Fallbacks:
        Вычисленный SHA-256 возвращается только для валидного объекта.
    """

    # Reject transport corruption before any object or metadata is persisted.
    storage = LocalVolumeDocumentStorage(tmp_path, 1_000)
    with pytest.raises(DocumentChecksumError):
        storage.put(
            uuid4(),
            uuid4(),
            b"%PDF-1.7\nchecksum",
            "application/pdf",
            "0" * 64,
        )


def test_storage_factory_selects_exactly_one_configured_backend(tmp_path: Path) -> None:
    """
    Проверяет явный выбор единственного storage adapter.

    Parameters:
        tmp_path (Path): Корень local backend.

    Returns:
        None: Factory возвращает adapter выбранного типа.

    Fallbacks:
        Неизвестное имя backend отклоняется Settings validation.
    """

    # Select adapters solely through the application configuration value.
    local = create_document_storage(
        Settings(document_storage_backend="local", document_storage_local_root=str(tmp_path))
    )
    s3 = create_document_storage(
        Settings(
            document_storage_backend="s3",
            document_storage_s3_bucket="research-documents",
            document_storage_s3_access_key_id="test",
            document_storage_s3_secret_access_key="test-secret",
        )
    )
    assert isinstance(local, LocalVolumeDocumentStorage)
    assert isinstance(s3, S3DocumentStorage)
    with pytest.raises(ValueError):
        Settings(document_storage_backend="both")
