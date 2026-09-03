import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import sessionmaker

from app.domain.research_job import ResearchJob, ResearchJobStatus
from app.providers.base import ScholarlyProvider
from app.repositories.citations import CitationRepository
from app.repositories.embeddings import EmbeddingRepository
from app.repositories.papers import PaperRepository, ProjectPaperRepository
from app.repositories.projects import ProjectRepository
from app.repositories.research_jobs import ResearchJobRepository
from app.repositories.semantic_scores import SemanticScoreRepository
from app.research.deduplication import PaperDeduplicator
from app.research.discovery import CitationDiscovery
from app.research.embeddings import EmbeddingService
from app.research.final_scoring import FinalRanker
from app.research.graph_analysis import GraphAnalyzer
from app.research.impact_ranking import ImpactRanker
from app.research.seed_resolution import SeedResolver
from app.research.semantic_ranking import SemanticRanker


class ResearchPipeline:
    """
    Оркестрирует discovery, persistence и semantic ranking проекта.

    Attributes:
        session_factory (sessionmaker): Фабрика SQLAlchemy sessions.
        provider (ScholarlyProvider): Scientific metadata provider.
        embedding_service (EmbeddingService): Scientific text encoder.

    Fallbacks:
        Любая fatal ошибка переводит ResearchJob в FAILED и сохраняет diagnostics.
    """

    def __init__(
        self,
        session_factory: sessionmaker,
        provider: ScholarlyProvider,
        embedding_service: EmbeddingService,
    ) -> None:
        """
        Создаёт pipeline с infrastructure dependencies.

        Parameters:
            session_factory (sessionmaker): Фабрика transaction sessions.
            provider (ScholarlyProvider): Scientific provider adapter.
            embedding_service (EmbeddingService): Versioned text encoder.

        Returns:
            None: Метод инициализирует pipeline.

        Fallbacks:
            Dependencies передаются явно для fixture-based tests.
        """

        self.session_factory = session_factory
        self.provider = provider
        self.embedding_service = embedding_service

    async def run(self, project_id: UUID, job_id: UUID) -> ResearchJob:
        """
        Выполняет текущие stages research pipeline для одного проекта.

        Parameters:
            project_id (UUID): Идентификатор ResearchProject.
            job_id (UUID): Идентификатор persistent ResearchJob.

        Returns:
            ResearchJob: Завершённое состояние job.

        Fallbacks:
            Fatal error сохраняется как FAILED и повторно поднимается worker boundary.
        """

        started_at = datetime.now(UTC)
        with self.session_factory() as session:
            jobs = ResearchJobRepository(session)
            try:
                # Load project inputs and expose the seed-resolution stage immediately.
                projects = ProjectRepository(session)
                config = projects.get_config(project_id)
                if config is None:
                    raise ValueError(f"Research project {project_id} was not found")
                identities = projects.get_seed_identities(project_id)
                if not identities:
                    raise ValueError("Research project has no Related Work entries")
                jobs.update(job_id, ResearchJobStatus.RESOLVING_SEEDS, 0.10)
                session.commit()

                resolver = SeedResolver(self.provider)
                resolution = await resolver.resolve_seed_papers(identities)
                if not resolution.resolved:
                    reasons = "; ".join(failure.reason for failure in resolution.failures)
                    raise ValueError(f"No seed papers were resolved: {reasons}")

                # Fetch complete global metadata for every successfully resolved seed.
                seed_ids = [paper.semantic_scholar_id for paper in resolution.resolved]
                seed_metadata = await self.provider.get_papers_batch(seed_ids)
                seed_metadata = PaperDeduplicator().deduplicate(seed_metadata)
                if not seed_metadata:
                    raise ValueError("Semantic Scholar returned no metadata for resolved seeds")
                jobs.update(
                    job_id,
                    ResearchJobStatus.DISCOVERING,
                    0.35,
                    papers_discovered=len(seed_metadata),
                )
                session.commit()

                # Expand both citation directions once and enforce project hard limits.
                discovery = await CitationDiscovery(self.provider).discover(seed_metadata, config)
                jobs.update(
                    job_id,
                    ResearchJobStatus.DISCOVERING,
                    0.70,
                    papers_discovered=len(discovery.papers),
                )
                session.commit()

                # Persist global entities first, then project membership and citation edges.
                papers = PaperRepository(session)
                project_papers = ProjectPaperRepository(session)
                citations = CitationRepository(session)
                global_ids = {}
                persistence_failures = []
                for discovered in discovery.papers:
                    try:
                        with session.begin_nested():
                            paper = papers.upsert(discovered.paper)
                            project_papers.upsert(
                                project_id=project_id,
                                paper_id=paper.id,
                                is_seed=discovered.is_seed,
                                depth=discovered.depth,
                            )
                        global_ids[discovered.paper.paper_id] = paper.id
                    except Exception as error:
                        persistence_failures.append(f"paper {discovered.paper.paper_id}: {error}")
                        logging.error(
                            json.dumps(
                                {
                                    "project_id": str(project_id),
                                    "job_id": str(job_id),
                                    "paper_id": discovered.paper.paper_id,
                                    "stage": "paper_persistence",
                                    "status": "failed",
                                    "error": str(error),
                                }
                            )
                        )
                if not global_ids:
                    raise ValueError("No discovered papers could be persisted")
                for edge in discovery.citations:
                    source_id = global_ids.get(edge.source_paper_id)
                    target_id = global_ids.get(edge.target_paper_id)
                    if source_id is not None and target_id is not None:
                        try:
                            with session.begin_nested():
                                citations.upsert(source_id, target_id)
                        except Exception as error:
                            persistence_failures.append(
                                f"citation {edge.source_paper_id}->{edge.target_paper_id}: {error}"
                            )
                            logging.error(
                                json.dumps(
                                    {
                                        "project_id": str(project_id),
                                        "job_id": str(job_id),
                                        "stage": "citation_persistence",
                                        "status": "failed",
                                        "error": str(error),
                                    }
                                )
                            )

                # Load reusable vectors and encode only papers missing this model version.
                jobs.update(
                    job_id,
                    ResearchJobStatus.EMBEDDING,
                    0.78,
                    papers_processed=len(global_ids),
                )
                session.commit()
                project_paper_entities = projects.get_papers(project_id)
                questions = projects.get_questions(project_id)
                seed_paper_ids = projects.get_seed_paper_ids(project_id)
                if not project_paper_entities:
                    raise ValueError("Research project has no persisted papers")
                if not questions:
                    raise ValueError("Research project has no research questions")

                embedding_repository = EmbeddingRepository(session)
                cached_embeddings = embedding_repository.get_many(
                    {paper.id for paper in project_paper_entities},
                    self.embedding_service.model_name,
                    self.embedding_service.model_version,
                    self.embedding_service.dimensions,
                )
                cached_ids = {embedding.paper_id for embedding in cached_embeddings}
                paper_embedding_batch = self.embedding_service.embed_papers(
                    [paper for paper in project_paper_entities if paper.id not in cached_ids]
                )
                embedding_failures = [
                    f"paper {failure.entity_id}: {failure.reason}"
                    for failure in paper_embedding_batch.failures
                ]
                persisted_embeddings = []
                for embedding in paper_embedding_batch.embeddings:
                    try:
                        with session.begin_nested():
                            embedding_repository.upsert(
                                embedding,
                                self.embedding_service.model_name,
                                self.embedding_service.model_version,
                                self.embedding_service.dimensions,
                            )
                        persisted_embeddings.append(embedding)
                    except Exception as error:
                        embedding_failures.append(
                            f"paper {embedding.paper_id} persistence: {error}"
                        )
                        logging.error(
                            json.dumps(
                                {
                                    "project_id": str(project_id),
                                    "job_id": str(job_id),
                                    "paper_id": str(embedding.paper_id),
                                    "stage": "embedding_persistence",
                                    "status": "failed",
                                    "error": str(error),
                                }
                            )
                        )
                paper_embeddings = cached_embeddings + persisted_embeddings
                question_embedding_batch = self.embedding_service.embed_questions(questions)
                embedding_failures.extend(
                    f"question {failure.entity_id}: {failure.reason}"
                    for failure in question_embedding_batch.failures
                )
                if not paper_embeddings:
                    raise ValueError("No paper embeddings could be created or loaded")
                if not question_embedding_batch.embeddings:
                    raise ValueError("No research question embeddings could be created")

                # Compute pair-level relevance and aggregate it without missing-as-zero bias.
                jobs.update(
                    job_id,
                    ResearchJobStatus.SCORING,
                    0.92,
                    papers_processed=len(paper_embeddings),
                )
                session.commit()
                ranking = SemanticRanker(
                    config.query_similarity_weight,
                    config.seed_similarity_weight,
                ).rank(
                    project_id,
                    paper_embeddings,
                    question_embedding_batch.embeddings,
                    seed_paper_ids,
                )
                semantic_scores = SemanticScoreRepository(session)
                scoring_failures = []
                question_scores_persisted = 0
                for score in ranking.question_scores:
                    try:
                        with session.begin_nested():
                            semantic_scores.upsert(score)
                        question_scores_persisted += 1
                    except Exception as error:
                        scoring_failures.append(
                            f"paper {score.paper_id}, question {score.question_id}: {error}"
                        )
                        logging.error(
                            json.dumps(
                                {
                                    "project_id": str(project_id),
                                    "job_id": str(job_id),
                                    "paper_id": str(score.paper_id),
                                    "question_id": str(score.question_id),
                                    "stage": "question_score_persistence",
                                    "status": "failed",
                                    "error": str(error),
                                }
                            )
                        )
                paper_scores_persisted = 0
                for score in ranking.paper_scores:
                    try:
                        with session.begin_nested():
                            project_papers.update_semantic_scores(
                                project_id,
                                score.paper_id,
                                score.query_similarity,
                                score.seed_similarity,
                                score.topic_score,
                            )
                        paper_scores_persisted += 1
                    except Exception as error:
                        scoring_failures.append(f"paper {score.paper_id}: {error}")
                        logging.error(
                            json.dumps(
                                {
                                    "project_id": str(project_id),
                                    "job_id": str(job_id),
                                    "paper_id": str(score.paper_id),
                                    "stage": "paper_score_persistence",
                                    "status": "failed",
                                    "error": str(error),
                                }
                            )
                        )
                if question_scores_persisted == 0 or paper_scores_persisted == 0:
                    raise ValueError("Semantic ranking scores could not be persisted")

                # Analyze the persisted project graph before impact and final scoring.
                jobs.update(
                    job_id,
                    ResearchJobStatus.GRAPH_ANALYSIS,
                    0.96,
                    papers_processed=len(paper_embeddings),
                )
                session.commit()
                project_scoring_entities = project_papers.get_many(project_id)
                project_paper_ids = {
                    project_paper.paper_id for project_paper in project_scoring_entities
                }
                project_citations = citations.get_for_papers(project_paper_ids)
                graph_metrics = GraphAnalyzer().analyze(
                    project_paper_ids,
                    project_citations,
                    seed_paper_ids,
                )
                impact_scores = ImpactRanker(
                    recency_tau=config.recency_tau,
                    citation_weight=config.impact_citation_weight,
                    recency_weight=config.impact_recency_weight,
                    pagerank_weight=config.impact_pagerank_weight,
                ).rank(
                    project_paper_entities,
                    graph_metrics,
                    datetime.now(UTC).year,
                )
                final_scores = FinalRanker(
                    topic_weight=config.topic_weight,
                    impact_weight=config.impact_weight,
                    graph_weight=config.graph_weight,
                    distance_weight=config.graph_distance_weight,
                    connectivity_weight=config.graph_connectivity_weight,
                ).rank(
                    project_scoring_entities,
                    graph_metrics,
                    impact_scores,
                )

                # Persist complete ranking results with per-paper failure isolation.
                graph_scoring_failures = []
                final_scores_persisted = 0
                for score in final_scores:
                    try:
                        with session.begin_nested():
                            project_papers.update_ranking_scores(project_id, score)
                        final_scores_persisted += 1
                    except Exception as error:
                        graph_scoring_failures.append(f"paper {score.paper_id}: {error}")
                        logging.error(
                            json.dumps(
                                {
                                    "project_id": str(project_id),
                                    "job_id": str(job_id),
                                    "paper_id": str(score.paper_id),
                                    "stage": "final_score_persistence",
                                    "status": "failed",
                                    "error": str(error),
                                }
                            )
                        )
                if final_scores_persisted == 0:
                    raise ValueError("Graph and final ranking scores could not be persisted")

                completed = jobs.update(
                    job_id,
                    ResearchJobStatus.COMPLETED,
                    1.0,
                    papers_discovered=len(discovery.papers),
                    papers_processed=len(global_ids),
                )
                session.commit()
                logging.info(
                    json.dumps(
                        {
                            "project_id": str(project_id),
                            "job_id": str(job_id),
                            "stage": "final_scoring",
                            "duration": (datetime.now(UTC) - started_at).total_seconds(),
                            "status": "completed",
                            "papers": len(global_ids),
                            "citations": len(project_citations),
                            "failures": len(resolution.failures)
                            + len(discovery.failures)
                            + len(persistence_failures)
                            + len(embedding_failures)
                            + len(scoring_failures)
                            + len(graph_scoring_failures),
                        }
                    )
                )
                return completed
            except Exception as error:
                # Roll back partial persistence and commit the observable FAILED state separately.
                session.rollback()
                try:
                    ResearchJobRepository(session).update(
                        job_id,
                        ResearchJobStatus.FAILED,
                        1.0,
                        error_message=str(error),
                    )
                    session.commit()
                except Exception:
                    session.rollback()
                    raise error from None
                logging.error(
                    json.dumps(
                        {
                            "project_id": str(project_id),
                            "job_id": str(job_id),
                            "stage": "research_pipeline",
                            "duration": (datetime.now(UTC) - started_at).total_seconds(),
                            "status": "failed",
                            "error": str(error),
                        }
                    )
                )
                raise
