from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from app.research.related_work_parser import RelatedWorkParseError, RelatedWorkParser


def test_parse_real_related_work_matrix() -> None:
    """
    Проверяет адаптацию реальных русскоязычных колонок проекта.

    Returns:
        None: Assertions подтверждают структуру первой строки.

    Fallbacks:
        Test failure показывает несовместимость parser с реальным XLSX.
    """

    # Exercise the repository sample instead of a simplified invented schema.
    entries = RelatedWorkParser().parse_file(Path("data/related_work_matrix.xlsx"))

    assert entries
    assert entries[0].local_id == "RW01"
    assert entries[0].title.startswith("FEVER:")
    assert entries[0].year == 2018
    assert entries[0].source == "https://aclanthology.org/N18-1074/"
    assert entries[0].literature_block == "Claim verification / evidence retrieval"
    assert entries[0].to_identity_input().local_id == "RW01"


def test_parse_xlsx_preserves_optional_annotations() -> None:
    """
    Проверяет преобразование optional researcher annotations.

    Returns:
        None: Assertions подтверждают значения DTO.

    Fallbacks:
        Test failure локализует потерю или смешивание annotation fields.
    """

    # Build an in-memory workbook so no temporary encoded file is needed.
    workbook = BytesIO()
    pd.DataFrame(
        [
            {
                "ID": "RW99",
                "Название": "A Paper",
                "Год": 2024,
                "Venue": "ACL",
                "Метод": "Graph method",
                "Ссылка / DOI / ACL Anthology / arXiv": "https://doi.org/10.1000/test",
            }
        ]
    ).to_excel(workbook, index=False)

    entry = RelatedWorkParser().parse_bytes(workbook.getvalue(), "related.xlsx")[0]

    assert entry.local_id == "RW99"
    assert entry.venue == "ACL"
    assert entry.method == "Graph method"
    assert entry.datasets is None


def test_parse_rejects_missing_required_columns() -> None:
    """
    Проверяет понятную ошибку при отсутствии Название.

    Returns:
        None: Assertion подтверждает domain-specific exception.

    Fallbacks:
        Test failure означает утечку низкоуровневой pandas ошибки.
    """

    # Create a structurally valid workbook with an invalid contract.
    workbook = BytesIO()
    pd.DataFrame([{"ID": "RW01"}]).to_excel(workbook, index=False)

    with pytest.raises(RelatedWorkParseError, match="Название"):
        RelatedWorkParser().parse_bytes(workbook.getvalue(), "related.xlsx")


def test_parse_rejects_duplicate_local_id() -> None:
    """
    Проверяет раннее обнаружение duplicate seed rows.

    Returns:
        None: Assertion подтверждает понятную duplicate ошибку.

    Fallbacks:
        Test failure предотвращает неоднозначную seed resolution.
    """

    # Duplicate IDs are rejected before persistence or provider calls.
    content = "ID,Название,Год\nRW01,First,2020\nRW01,Second,2021\n".encode()

    with pytest.raises(RelatedWorkParseError, match="Duplicate"):
        RelatedWorkParser().parse_bytes(content, "related.csv")
