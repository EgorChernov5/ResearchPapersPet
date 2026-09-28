from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ResearchConfigPayload(BaseModel):
    """
    HTTP contract project research configuration.

    Fallbacks:
        Domain ResearchConfig выполняет cross-field weight validation.
    """

    model_config = ConfigDict(from_attributes=True)

    max_depth: int = Field(default=2, ge=1, le=5)
    max_papers: int = Field(default=300, ge=1)
    top_k_expansion: int = Field(default=20, ge=1)
    min_year: int | None = Field(default=None, ge=1000)
    expand_references_topic_threshold: float = Field(default=0.75, ge=0, le=1)
    pdf_top_n: int = Field(default=20, ge=0)
    allow_manual_pdf_upload: bool = False
    topic_weight: float = Field(default=0.60, ge=0)
    impact_weight: float = Field(default=0.25, ge=0)
    graph_weight: float = Field(default=0.15, ge=0)
    query_similarity_weight: float = Field(default=0.70, ge=0)
    seed_similarity_weight: float = Field(default=0.30, ge=0)
    impact_citation_weight: float = Field(default=0.50, ge=0)
    impact_recency_weight: float = Field(default=0.20, ge=0)
    impact_pagerank_weight: float = Field(default=0.30, ge=0)
    graph_distance_weight: float = Field(default=0.60, ge=0)
    graph_connectivity_weight: float = Field(default=0.40, ge=0)
    recency_tau: float = Field(default=5.0, gt=0)


class CreateProjectRequest(BaseModel):
    """
    HTTP request создания research project.

    Fallbacks:
        Пустое имя отклоняется Pydantic до application layer.
    """

    name: str = Field(min_length=1, max_length=255)
    config: ResearchConfigPayload = Field(default_factory=ResearchConfigPayload)


class ResearchQuestionResponse(BaseModel):
    """
    HTTP response одного research question.

    Fallbacks:
        Сериализация использует domain attributes.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    text: str


class ResearchQuestionsRequest(BaseModel):
    """
    HTTP request добавления research questions.

    Fallbacks:
        Пустой список отклоняется Pydantic validation.
    """

    questions: list[str] = Field(min_length=1)


class ResearchQuestionsResponse(BaseModel):
    """
    HTTP response созданных research questions.

    Fallbacks:
        Пустой response не формируется application use case.
    """

    questions: list[ResearchQuestionResponse]


class ResearchProjectResponse(BaseModel):
    """
    HTTP representation project setup.

    Fallbacks:
        Проект без вопросов возвращает пустой questions list.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    config: ResearchConfigPayload
    questions: list[ResearchQuestionResponse]


class RelatedWorkUploadResponse(BaseModel):
    """
    HTTP confirmation сохранённого Related Work upload.

    Fallbacks:
        Invalid upload возвращается HTTP error до response construction.
    """

    project_id: UUID
    entries_count: int


class ResearchJobResponse(BaseModel):
    """
    HTTP representation observable background job state.

    Fallbacks:
        Незавершённые timestamps и error_message остаются None.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    status: str
    progress: float
    papers_discovered: int
    papers_processed: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None


class PaperResponse(BaseModel):
    """
    HTTP representation global metadata и project-specific ranking.

    Fallbacks:
        Missing metadata и незавершённые scores сериализуются как null.
    """

    model_config = ConfigDict(from_attributes=True)

    paper_id: UUID
    semantic_scholar_id: str | None
    title: str
    abstract: str | None
    year: int | None
    citation_count: int | None
    influential_citation_count: int | None
    reference_count: int | None
    authors: list[str]
    categories: list[str]
    pdf_url: str | None
    is_seed: bool
    depth: int | None
    query_similarity: float | None
    seed_similarity: float | None
    topic_score: float | None
    citation_score: float | None
    recency_score: float | None
    impact_score: float | None
    distance_score: float | None
    connectivity_score: float | None
    pagerank_score: float | None
    graph_score: float | None
    final_score: float | None


class PaperListResponse(BaseModel):
    """
    HTTP collection ranked papers.

    Fallbacks:
        Project без результатов возвращает count=0 и пустой papers list.
    """

    count: int
    papers: list[PaperResponse]


class PaperQuestionScoreResponse(BaseModel):
    """
    HTTP representation paper × question semantic score.

    Fallbacks:
        Missing similarities сериализуются как null.
    """

    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    paper_id: UUID
    question_id: UUID
    query_similarity: float | None
    topic_score: float | None


class PaperDetailsResponse(BaseModel):
    """
    HTTP paper details с pair-level question scores.

    Fallbacks:
        Отсутствующие question scores возвращаются пустым списком.
    """

    paper: PaperResponse
    question_scores: list[PaperQuestionScoreResponse]


class GraphEdgeResponse(BaseModel):
    """
    HTTP directed citation edge source cites target.

    Fallbacks:
        Graph use case исключает edges вне filtered nodes.
    """

    source_paper_id: UUID
    target_paper_id: UUID


class GraphResponse(BaseModel):
    """
    HTTP project graph для будущего Cytoscape client.

    Fallbacks:
        Empty filtered graph возвращает пустые nodes и edges.
    """

    nodes: list[PaperResponse]
    edges: list[GraphEdgeResponse]
