from app.domain.embedding import EmbeddedPaper, EmbeddedQuestion
from app.domain.paper import Paper, ProviderPaper
from app.domain.project import ResearchQuestion
from app.repositories.embeddings import EmbeddingRepository
from app.repositories.papers import PaperRepository
from app.research.balanced_selection import BalancedPaperSelector
from app.research.embeddings import EmbeddingService
from app.research.semantic_ranking import SemanticRanker
from app.research.structures import (
    DiscoverySelection,
    PreliminaryCandidateScore,
    PreliminaryQuestionShortlist,
    PreliminaryScoringResult,
)


class PreliminarySemanticScorer:
    """
    Строит per-question shortlists только по query и seed similarity.

    Attributes:
        semantic_ranker (SemanticRanker): Общая реализация cosine и missing-value policy.

    Fallbacks:
        Недоступные компоненты исключаются с перенормировкой доступных weights.
    """

    def __init__(self, query_weight: float, seed_weight: float) -> None:
        """
        Настраивает веса preliminary topic score.

        Parameters:
            query_weight (float): Вес similarity с research question.
            seed_weight (float): Вес максимальной similarity с seed papers.

        Returns:
            None: Метод инициализирует scorer.

        Fallbacks:
            Некорректные weights отклоняет существующий SemanticRanker contract.
        """

        self.semantic_ranker = SemanticRanker(query_weight, seed_weight)

    def rank(
        self,
        candidate_embeddings: list[EmbeddedPaper],
        question_embeddings: list[EmbeddedQuestion],
        seed_embeddings: list[EmbeddedPaper],
        top_k: int,
    ) -> PreliminaryScoringResult:
        """
        Рассчитывает и сортирует независимый shortlist каждого вопроса.

        Parameters:
            candidate_embeddings (list[EmbeddedPaper]): Vectors кандидатов уровня.
            question_embeddings (list[EmbeddedQuestion]): Vectors research questions.
            seed_embeddings (list[EmbeddedPaper]): Доступные global seed vectors.
            top_k (int): Максимальный размер каждого shortlist.

        Returns:
            PreliminaryScoringResult: Per-question ranked shortlists.

        Fallbacks:
            Zero-norm и missing seed vectors дают None согласно общей semantic policy.
        """

        if top_k < 1:
            raise ValueError("Preliminary shortlist top_k must be positive")

        # Compute the candidate-to-seed signal once because it is question-independent.
        seed_similarity_by_paper = {}
        for candidate in candidate_embeddings:
            similarities = [
                self.semantic_ranker.cosine_similarity(candidate.vector, seed.vector)
                for seed in seed_embeddings
            ]
            seed_similarity_by_paper[candidate.paper_id] = max(
                (value for value in similarities if value is not None),
                default=None,
            )

        # Rank the same candidate pool independently for every research question.
        result = PreliminaryScoringResult()
        for question in question_embeddings:
            candidates = []
            for candidate in candidate_embeddings:
                query_similarity = self.semantic_ranker.cosine_similarity(
                    candidate.vector,
                    question.vector,
                )
                seed_similarity = seed_similarity_by_paper[candidate.paper_id]
                preliminary_topic_score = self.semantic_ranker.weighted_average_available(
                    {
                        "query_similarity": query_similarity,
                        "seed_similarity": seed_similarity,
                    },
                    {
                        "query_similarity": self.semantic_ranker.query_weight,
                        "seed_similarity": self.semantic_ranker.seed_weight,
                    },
                )
                candidates.append(
                    PreliminaryCandidateScore(
                        paper_id=candidate.paper_id,
                        question_id=question.question_id,
                        query_similarity=query_similarity,
                        seed_similarity=seed_similarity,
                        preliminary_topic_score=preliminary_topic_score,
                    )
                )
            candidates.sort(
                key=lambda score: (
                    score.preliminary_topic_score is None,
                    -(score.preliminary_topic_score or 0.0),
                    str(score.paper_id),
                )
            )
            result.shortlists.append(
                PreliminaryQuestionShortlist(question.question_id, candidates[:top_k])
            )
        return result


class PreliminaryScoringService:
    """
    Оркестрирует global embedding cache и preliminary semantic scorer.

    Attributes:
        embedding_service (EmbeddingService): Versioned scientific text encoder.
        embedding_repository (EmbeddingRepository): PostgreSQL/pgvector cache.
        scorer (PreliminarySemanticScorer): Чистый preliminary ranking component.

    Fallbacks:
        Статья с неуспешным embedding исключается из shortlists без project persistence.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        embedding_repository: EmbeddingRepository,
        scorer: PreliminarySemanticScorer,
    ) -> None:
        """
        Собирает зависимости preliminary scoring.

        Parameters:
            embedding_service (EmbeddingService): Versioned scientific text encoder.
            embedding_repository (EmbeddingRepository): Global embedding cache.
            scorer (PreliminarySemanticScorer): Preliminary ranking algorithm.

        Returns:
            None: Метод сохраняет зависимости.

        Fallbacks:
            Transaction lifecycle остаётся responsibility вызывающего кода.
        """

        self.embedding_service = embedding_service
        self.embedding_repository = embedding_repository
        self.scorer = scorer

    def rank(
        self,
        candidates: list[Paper],
        seed_papers: list[Paper],
        questions: list[ResearchQuestion],
        top_k: int,
    ) -> PreliminaryScoringResult:
        """
        Загружает или создаёт embeddings и возвращает per-question shortlists.

        Parameters:
            candidates (list[Paper]): Metadata дедуплицированных кандидатов уровня.
            seed_papers (list[Paper]): Metadata seed papers проекта.
            questions (list[ResearchQuestion]): Research questions проекта.
            top_k (int): Максимальный размер shortlist каждого вопроса.

        Returns:
            PreliminaryScoringResult: Независимые ranked shortlists.

        Fallbacks:
            Cached vectors используются повторно, а failures не создают zero vectors.
        """

        # Load compatible global vectors and encode only papers absent from the cache.
        papers_by_id = {paper.id: paper for paper in [*seed_papers, *candidates]}
        cached_embeddings = self.embedding_repository.get_many(
            set(papers_by_id),
            self.embedding_service.model_name,
            self.embedding_service.model_version,
            self.embedding_service.dimensions,
        )
        cached_ids = {embedding.paper_id for embedding in cached_embeddings}
        created_batch = self.embedding_service.embed_papers(
            [paper for paper_id, paper in papers_by_id.items() if paper_id not in cached_ids]
        )
        for embedding in created_batch.embeddings:
            self.embedding_repository.upsert(
                embedding,
                self.embedding_service.model_name,
                self.embedding_service.model_version,
                self.embedding_service.dimensions,
            )

        # Questions share the same model space but remain project-specific and uncached.
        paper_embeddings = cached_embeddings + created_batch.embeddings
        candidate_ids = {paper.id for paper in candidates}
        seed_ids = {paper.id for paper in seed_papers}
        question_batch = self.embedding_service.embed_questions(questions)
        return self.scorer.rank(
            [embedding for embedding in paper_embeddings if embedding.paper_id in candidate_ids],
            question_batch.embeddings,
            [embedding for embedding in paper_embeddings if embedding.paper_id in seed_ids],
            top_k,
        )


class DiscoveryCandidateSelector:
    """
    Связывает provider metadata с global embedding cache и balanced selector.

    Attributes:
        paper_repository (PaperRepository): Global paper metadata repository.
        scoring_service (PreliminaryScoringService): Preliminary semantic orchestration.
        selector (BalancedPaperSelector): Детерминированный per-question selector.

    Fallbacks:
        Papers без embeddings не попадают в следующий frontier.
    """

    def __init__(
        self,
        paper_repository: PaperRepository,
        scoring_service: PreliminaryScoringService,
        selector: BalancedPaperSelector,
    ) -> None:
        """
        Создаёт adapter выбора provider candidates.

        Parameters:
            paper_repository (PaperRepository): Global metadata repository.
            scoring_service (PreliminaryScoringService): Preliminary scoring service.
            selector (BalancedPaperSelector): Balanced paper selector.

        Returns:
            None: Метод сохраняет зависимости.

        Fallbacks:
            Transaction lifecycle остаётся responsibility pipeline.
        """

        self.paper_repository = paper_repository
        self.scoring_service = scoring_service
        self.selector = selector

    def select(
        self,
        candidates: list[ProviderPaper],
        seeds: list[ProviderPaper],
        questions: list[ResearchQuestion],
        limit: int,
    ) -> DiscoverySelection:
        """
        Оценивает дедуплицированных кандидатов и выбирает следующий frontier.

        Parameters:
            candidates (list[ProviderPaper]): Кандидаты текущего уровня.
            seeds (list[ProviderPaper]): Seed metadata проекта.
            questions (list[ResearchQuestion]): Research questions проекта.
            limit (int): Глобальный лимит уровня.

        Returns:
            DiscoverySelection: Выбранные provider papers и их лучшие scores.

        Fallbacks:
            Пустой candidate list возвращает пустой selection без embedding calls.
        """

        if not candidates or limit < 1:
            return DiscoverySelection()

        # Persist global metadata so compatible embeddings can be reused across projects.
        candidate_entities = [self.paper_repository.upsert(paper) for paper in candidates]
        seed_entities = [self.paper_repository.upsert(paper) for paper in seeds]
        provider_by_id = {
            entity.id: provider
            for entity, provider in zip(candidate_entities, candidates, strict=True)
        }

        # Score candidates independently per question, then apply the shared balanced policy.
        scoring_result = self.scoring_service.rank(
            candidate_entities,
            seed_entities,
            questions,
            top_k=limit,
        )
        selected_ids = self.selector.select(scoring_result, limit)
        preliminary_scores = {}
        for shortlist in scoring_result.shortlists:
            for candidate in shortlist.candidates:
                provider = provider_by_id.get(candidate.paper_id)
                if provider is None:
                    continue
                current = preliminary_scores.get(provider.paper_id)
                score = candidate.preliminary_topic_score
                if score is not None and (current is None or score > current):
                    preliminary_scores[provider.paper_id] = score
                elif provider.paper_id not in preliminary_scores:
                    preliminary_scores[provider.paper_id] = None
        return DiscoverySelection(
            papers=[provider_by_id[paper_id] for paper_id in selected_ids],
            preliminary_scores=preliminary_scores,
        )
