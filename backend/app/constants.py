# Map the real Related Work matrix columns into stable domain field names.
RELATED_WORK_COLUMNS = {
    "ID": "local_id",
    "Название": "title",
    "Год": "year",
    "Venue": "venue",
    "Блок литературы": "literature_block",
    "Задача": "task",
    "Метод": "method",
    "Датасеты": "datasets",
    "Метрики": "metrics",
    "Код открыт?": "code_available",
    "Данные открыты?": "data_available",
    "Чем полезно для нашей статьи": "usefulness",
    "Что можно реализовать / сравнить": "comparison_ideas",
    "BibTeX key": "bibtex_key",
    "Ссылка / DOI / ACL Anthology / arXiv": "source",
}

# Request only fields required by the current domain and future citation discovery.
SEMANTIC_SCHOLAR_PAPER_FIELDS = (
    "paperId",
    "externalIds",
    "title",
    "abstract",
    "year",
    "citationCount",
    "influentialCitationCount",
    "referenceCount",
    "authors",
    "s2FieldsOfStudy",
    "openAccessPdf",
)

# Persist only identifiers supported by the current global Paper contract.
SUPPORTED_EXTERNAL_IDENTIFIER_PROVIDERS = (
    "semantic_scholar",
    "doi",
    "arxiv",
    "acl",
)

# Allow API sorting only by stable paper metadata and persisted project scores.
PAPER_RANKING_SORT_FIELDS = (
    "final_score",
    "topic_score",
    "impact_score",
    "graph_score",
    "citation_count",
    "year",
    "depth",
    "title",
)
