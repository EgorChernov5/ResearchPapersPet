from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DownloadedDocument:
    """
    Проверенный HTTP-ответ с PDF до object storage validation.

    Attributes:
        content (bytes): Полное содержимое PDF.
        media_type (str): Нормализованный response Content-Type.
        checksum (str): SHA-256 загруженного содержимого.

    Fallbacks:
        Downloader не создаёт объект при invalid status, MIME, signature или размере.
    """

    content: bytes
    media_type: str
    checksum: str
