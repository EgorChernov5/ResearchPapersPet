import re
import unicodedata

from app.domain.paper import ProviderPaper


class PaperDeduplicator:
    """
    Дедуплицирует provider papers по canonical identifiers и title fallback.

    Fallbacks:
        Нормализованный title используется только как последний доступный ключ.
    """

    def normalize_title(self, title: str) -> str:
        """
        Нормализует название для последнего deduplication fallback.

        Parameters:
            title (str): Исходное название статьи.

        Returns:
            str: Lowercase alphanumeric title с одиночными пробелами.

        Fallbacks:
            Пустой title возвращает пустую строку и не создаёт ключ.
        """

        normalized = unicodedata.normalize("NFKC", title).casefold()
        normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
        return " ".join(normalized.split())

    def deduplicate(self, papers: list[ProviderPaper]) -> list[ProviderPaper]:
        """
        Объединяет duplicate papers с сохранением наиболее полных metadata.

        Parameters:
            papers (list[ProviderPaper]): Provider papers в исходном порядке.

        Returns:
            list[ProviderPaper]: Уникальные papers в стабильном порядке.

        Fallbacks:
            Missing metadata дополняются из duplicate record, а не заменяются нулями.
        """

        unique_papers = []
        identity_indexes = {}

        # Resolve every candidate against identifiers in the required priority order.
        for paper in papers:
            external_ids = {key.casefold(): value for key, value in paper.external_ids.items()}
            identities = [
                ("semantic_scholar", paper.paper_id),
                ("doi", external_ids.get("doi")),
                ("arxiv", external_ids.get("arxiv")),
                ("acl", external_ids.get("acl")),
                ("title", self.normalize_title(paper.title)),
            ]
            identities = [(provider, value) for provider, value in identities if value]
            duplicate_index = next(
                (
                    identity_indexes[identity]
                    for identity in identities
                    if identity in identity_indexes
                ),
                None,
            )

            if duplicate_index is None:
                duplicate_index = len(unique_papers)
                unique_papers.append(paper)
            else:
                # Preserve the canonical first record and fill only missing metadata.
                existing = unique_papers[duplicate_index]
                existing.external_ids.update(
                    {
                        key: value
                        for key, value in paper.external_ids.items()
                        if key not in existing.external_ids and value
                    }
                )
                for attribute in (
                    "abstract",
                    "year",
                    "citation_count",
                    "influential_citation_count",
                    "reference_count",
                    "pdf_url",
                ):
                    if (
                        getattr(existing, attribute) is None
                        and getattr(paper, attribute) is not None
                    ):
                        setattr(existing, attribute, getattr(paper, attribute))
                if not existing.authors and paper.authors:
                    existing.authors = list(paper.authors)
                if not existing.categories and paper.categories:
                    existing.categories = list(paper.categories)

            # Map every available identity to the retained canonical record.
            for identity in identities:
                identity_indexes[identity] = duplicate_index

        return unique_papers
