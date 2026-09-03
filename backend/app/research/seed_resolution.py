import re
import unicodedata
from difflib import SequenceMatcher

from app.domain.related_work import PaperIdentityInput
from app.domain.seed import (
    ResolvedSeedPaper,
    SeedResolutionFailure,
    SeedResolutionResult,
)
from app.providers.base import (
    ScholarlyPaperNotFoundError,
    ScholarlyProvider,
    ScholarlyProviderError,
)


class SeedResolver:
    """
    Разрешает Related Work identities в canonical Semantic Scholar papers.

    Attributes:
        provider (ScholarlyProvider): Scientific metadata provider.
        min_id_title_similarity (float): Минимум validation для ID lookup.
        min_search_title_similarity (float): Минимум validation для title search.

    Fallbacks:
        Unresolved и duplicate seeds записываются как failures без остановки batch.
    """

    def __init__(
        self,
        provider: ScholarlyProvider,
        min_id_title_similarity: float = 0.80,
        min_search_title_similarity: float = 0.90,
        year_tolerance: int = 1,
    ) -> None:
        """
        Настраивает resolver validation thresholds.

        Parameters:
            provider (ScholarlyProvider): Scientific provider adapter.
            min_id_title_similarity (float): ID lookup threshold. По умолчанию: 0.80.
            min_search_title_similarity (float): Search threshold. По умолчанию: 0.90.
            year_tolerance (int): Допустимая разница годов. По умолчанию: 1.

        Returns:
            None: Метод инициализирует resolver.

        Fallbacks:
            Invalid thresholds отклоняются ValueError до внешних requests.
        """

        if not 0 <= min_id_title_similarity <= 1:
            raise ValueError("min_id_title_similarity must be between 0 and 1")
        if not 0 <= min_search_title_similarity <= 1:
            raise ValueError("min_search_title_similarity must be between 0 and 1")
        if year_tolerance < 0:
            raise ValueError("year_tolerance must not be negative")
        self.provider = provider
        self.min_id_title_similarity = min_id_title_similarity
        self.min_search_title_similarity = min_search_title_similarity
        self.year_tolerance = year_tolerance

    def extract_identifier(self, source: str | None) -> tuple[str | None, str | None]:
        """
        Извлекает лучший canonical identifier из source без API request.

        Parameters:
            source (str | None): URL или raw identifier.

        Returns:
            tuple[str | None, str | None]: Resolution method и prefixed identifier.

        Fallbacks:
            Неизвестный или пустой source возвращает (None, None) для title search.
        """

        if not source or not source.strip():
            return None, None
        value = source.strip()

        # Apply the required priority independently of URL formatting.
        semantic_match = re.search(
            r"(?:semanticscholar\.org/(?:paper/[^/]+/|paper/)|^)([0-9a-fA-F]{40})(?:[/?#]|$)",
            value,
            re.IGNORECASE,
        )
        corpus_match = re.search(r"(?:CorpusID:|corpus/)(\d+)", value, re.IGNORECASE)
        if semantic_match:
            return "semantic_scholar_id", semantic_match.group(1)
        if corpus_match:
            return "semantic_scholar_id", f"CorpusID:{corpus_match.group(1)}"

        doi_match = re.search(
            r"(?:doi\.org/|^DOI:\s*|^)(10\.\d{4,9}/[^\s?#]+)",
            value,
            re.IGNORECASE,
        )
        if doi_match:
            doi = doi_match.group(1).rstrip(".,;)")
            return "doi", f"DOI:{doi}"

        arxiv_match = re.search(
            r"(?:arxiv\.org/(?:abs|pdf)/|^ARXIV:\s*|^)(\d{4}\.\d{4,5}(?:v\d+)?)(?:\.pdf)?(?:[/?#]|$)",
            value,
            re.IGNORECASE,
        )
        if arxiv_match:
            return "arxiv", f"ARXIV:{arxiv_match.group(1)}"

        acl_match = re.search(
            r"(?:aclanthology\.org/|^ACL:\s*)([A-Za-z0-9][A-Za-z0-9.-]+)(?:[/?#]|$)",
            value,
            re.IGNORECASE,
        )
        if acl_match:
            return "acl", f"ACL:{acl_match.group(1).rstrip('.')}"
        return None, None

    def normalize_title(self, title: str) -> str:
        """
        Нормализует title для deterministic validation и deduplication.

        Parameters:
            title (str): Исходное название статьи.

        Returns:
            str: Lowercase alphanumeric title с одиночными пробелами.

        Fallbacks:
            Пустой title возвращает пустую строку и не проходит validation.
        """

        normalized = unicodedata.normalize("NFKC", title).casefold()
        normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
        return " ".join(normalized.split())

    def title_similarity(self, expected: str, actual: str) -> float:
        """
        Вычисляет normalized title similarity.

        Parameters:
            expected (str): Title из Related Work.
            actual (str): Canonical provider title.

        Returns:
            float: Sequence similarity от 0 до 1.

        Fallbacks:
            Пустой normalized title даёт 0.
        """

        expected_normalized = self.normalize_title(expected)
        actual_normalized = self.normalize_title(actual)
        if not expected_normalized or not actual_normalized:
            return 0.0
        return SequenceMatcher(None, expected_normalized, actual_normalized).ratio()

    def is_year_compatible(self, expected: int | None, actual: int | None) -> bool:
        """
        Проверяет publication year с configured tolerance.

        Parameters:
            expected (int | None): Год из Related Work.
            actual (int | None): Год provider paper.

        Returns:
            bool: True для compatible или missing year.

        Fallbacks:
            Missing year не превращает релевантность в автоматический failure.
        """

        if expected is None or actual is None:
            return True
        return abs(expected - actual) <= self.year_tolerance

    async def resolve_seed_papers(
        self,
        identities: list[PaperIdentityInput],
    ) -> SeedResolutionResult:
        """
        Разрешает seed papers с per-paper failure isolation.

        Parameters:
            identities (list[PaperIdentityInput]): Минимальные seed identities.

        Returns:
            SeedResolutionResult: Успехи и failures всего batch.

        Fallbacks:
            Provider error одной статьи записывается и не прерывает следующие seeds.
        """

        result = SeedResolutionResult()
        seen_paper_ids = set()

        # Resolve each seed independently so one provider failure cannot break the project.
        for identity in identities:
            try:
                method, identifier = self.extract_identifier(identity.source)
                paper = None
                confidence = 0.0

                # Prefer canonical identifiers but validate title and year after lookup.
                if identifier:
                    try:
                        candidate = await self.provider.get_paper(identifier)
                    except ScholarlyPaperNotFoundError:
                        candidate = None
                    if candidate is not None:
                        similarity = self.title_similarity(identity.title, candidate.title)
                        if similarity >= self.min_id_title_similarity and self.is_year_compatible(
                            identity.year, candidate.year
                        ):
                            paper = candidate
                            confidence = 0.85 * similarity + 0.15

                # Try exact normalized-title equality before a fuzzy search decision.
                if paper is None:
                    search_results = await self.provider.search_papers(
                        identity.title,
                        limit=10,
                    )
                    exact_candidates = [
                        candidate
                        for candidate in search_results
                        if self.normalize_title(candidate.title)
                        == self.normalize_title(identity.title)
                        and self.is_year_compatible(identity.year, candidate.year)
                    ]
                    if exact_candidates:
                        paper = min(
                            exact_candidates,
                            key=lambda candidate: (
                                abs((candidate.year or identity.year or 0) - (identity.year or 0)),
                                candidate.paper_id,
                            ),
                        )
                        method = "title_search"
                        confidence = 1.0 if paper.year == identity.year else 0.97

                # Use normalized title plus year as the final controlled fallback.
                if paper is None:
                    normalized_query = self.normalize_title(identity.title)
                    fuzzy_results = await self.provider.search_papers(
                        normalized_query,
                        limit=10,
                        year=identity.year,
                    )
                    compatible_candidates = [
                        candidate
                        for candidate in fuzzy_results
                        if self.is_year_compatible(identity.year, candidate.year)
                    ]
                    if compatible_candidates:
                        candidate = max(
                            compatible_candidates,
                            key=lambda item: self.title_similarity(identity.title, item.title),
                        )
                        similarity = self.title_similarity(identity.title, candidate.title)
                        if similarity >= self.min_search_title_similarity:
                            paper = candidate
                            method = "title_search"
                            confidence = 0.90 * similarity + 0.10

                if paper is None:
                    result.failures.append(
                        SeedResolutionFailure(
                            local_id=identity.local_id,
                            reason="No Semantic Scholar paper passed title and year validation",
                            original_source=identity.source,
                        )
                    )
                    continue
                if paper.paper_id in seen_paper_ids:
                    result.failures.append(
                        SeedResolutionFailure(
                            local_id=identity.local_id,
                            reason=f"Duplicate seed resolves to {paper.paper_id}",
                            original_source=identity.source,
                        )
                    )
                    continue

                # Preserve all external identifiers and guarantee the canonical S2 identifier.
                seen_paper_ids.add(paper.paper_id)
                external_ids = dict(paper.external_ids)
                external_ids.setdefault("semantic_scholar", paper.paper_id)
                result.resolved.append(
                    ResolvedSeedPaper(
                        local_id=identity.local_id,
                        paper_id=paper.paper_id,
                        semantic_scholar_id=paper.paper_id,
                        title=paper.title,
                        year=paper.year,
                        external_ids=external_ids,
                        resolution_method=method or "title_search",
                        resolution_confidence=round(min(confidence, 1.0), 4),
                        original_source=identity.source,
                    )
                )
            except ScholarlyProviderError as error:
                result.failures.append(
                    SeedResolutionFailure(
                        local_id=identity.local_id,
                        reason=str(error),
                        original_source=identity.source,
                    )
                )

        return result
