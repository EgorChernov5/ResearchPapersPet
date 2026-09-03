from datetime import UTC, datetime
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd

from app.constants import RELATED_WORK_COLUMNS
from app.domain.related_work import RelatedWorkEntry


class RelatedWorkParseError(ValueError):
    """
    Понятная ошибка структуры или содержимого Related Work.

    Fallbacks:
        API layer может преобразовать исключение в HTTP 422 без потери причины.
    """


class RelatedWorkParser:
    """
    Преобразует XLSX или CSV Related Work в доменные entries.

    Attributes:
        required_columns (set[str]): Обязательные исходные колонки.

    Fallbacks:
        Invalid, empty или неполный файл отклоняется RelatedWorkParseError.
    """

    required_columns = {"ID", "Название"}

    def parse_file(self, path: Path) -> list[RelatedWorkEntry]:
        """
        Читает Related Work из файла проекта.

        Parameters:
            path (Path): Путь к XLSX или CSV.

        Returns:
            list[RelatedWorkEntry]: Проверенные строки Related Work.

        Fallbacks:
            Ошибки формата оборачиваются в RelatedWorkParseError.
        """

        try:
            content = path.read_bytes()
        except OSError as error:
            raise RelatedWorkParseError(f"Cannot read Related Work file: {error}") from error
        return self.parse_bytes(content, path.name)

    def parse_bytes(self, content: bytes, filename: str) -> list[RelatedWorkEntry]:
        """
        Читает загруженный XLSX или CSV из памяти.

        Parameters:
            content (bytes): Содержимое пользовательского файла.
            filename (str): Имя файла для выбора parser backend.

        Returns:
            list[RelatedWorkEntry]: Проверенные доменные entries.

        Fallbacks:
            Invalid encoding, workbook или columns дают RelatedWorkParseError.
        """

        if not content:
            raise RelatedWorkParseError("Related Work file is empty")

        # Parse only the two supported tabular input formats.
        suffix = Path(filename).suffix.lower()
        try:
            if suffix == ".xlsx":
                workbook = pd.ExcelFile(BytesIO(content), engine="openpyxl")
                frame = None
                matched_columns = -1
                for sheet_name in workbook.sheet_names:
                    candidate = workbook.parse(sheet_name=sheet_name)
                    candidate_matches = len(self.required_columns.intersection(candidate.columns))
                    if candidate_matches > matched_columns:
                        frame = candidate
                        matched_columns = candidate_matches
                    if self.required_columns.issubset(candidate.columns):
                        frame = candidate
                        break
            elif suffix == ".csv":
                frame = pd.read_csv(StringIO(content.decode("utf-8-sig")))
            else:
                raise RelatedWorkParseError("Related Work must be an .xlsx or .csv file")
        except RelatedWorkParseError:
            raise
        except (UnicodeError, ValueError, OSError) as error:
            raise RelatedWorkParseError(
                f"Invalid Related Work {suffix or 'file'}: {error}"
            ) from error

        if frame is None:
            raise RelatedWorkParseError("Related Work workbook contains no worksheets")

        # Validate the stable identification columns before row conversion.
        missing_columns = self.required_columns.difference(frame.columns)
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise RelatedWorkParseError(f"Missing required columns: {missing}")
        if frame.empty:
            raise RelatedWorkParseError("Related Work contains no entries")

        # Convert real matrix columns while preserving optional researcher annotations.
        entries = []
        seen_local_ids = set()
        current_year = datetime.now(UTC).year
        for row_number, row in frame.iterrows():
            values = {}
            for column, field_name in RELATED_WORK_COLUMNS.items():
                value = row.get(column)
                if pd.isna(value) or (isinstance(value, str) and not value.strip()):
                    values[field_name] = None
                elif field_name == "year":
                    try:
                        numeric_year = float(value)
                    except (TypeError, ValueError) as error:
                        raise RelatedWorkParseError(
                            f"Row {row_number + 2}: year must be an integer"
                        ) from error
                    if (
                        not numeric_year.is_integer()
                        or not 1000 <= numeric_year <= current_year + 1
                    ):
                        raise RelatedWorkParseError(
                            f"Row {row_number + 2}: year is outside the supported range"
                        )
                    values[field_name] = int(numeric_year)
                else:
                    values[field_name] = str(value).strip()

            local_id = values.get("local_id")
            title = values.get("title")
            if not local_id or not title:
                raise RelatedWorkParseError(
                    f"Row {row_number + 2}: ID and Название must not be empty"
                )
            if local_id in seen_local_ids:
                raise RelatedWorkParseError(f"Duplicate Related Work ID: {local_id}")
            seen_local_ids.add(local_id)
            entries.append(RelatedWorkEntry(**values))

        return entries
