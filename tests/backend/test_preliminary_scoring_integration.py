from math import sqrt
from uuid import uuid4

import pytest
from app.config import Settings
from app.domain.paper import Paper
from app.domain.project import ResearchQuestion
from app.infrastructure.database import Database
from app.infrastructure.models import PaperEmbeddingModel, PaperModel
from app.repositories.embeddings import EmbeddingRepository
from app.research.embeddings import EmbeddingService
from app.research.preliminary_scoring import (
    PreliminaryScoringService,
    PreliminarySemanticScorer,
)
from sqlalchemy import delete


@pytest.mark.service_integration
def test_preliminary_scoring_uses_real_specter_and_pgvector_cache() -> None:
    """
    Проверяет настоящую SPECTER → PostgreSQL/pgvector embedding-цепочку.

    Returns:
        None: Vector нормализован, имеет 768 измерений и повторно читается из cache.

    Fallbacks:
        Тест требует PostgreSQL с migrations и доступной локально или через сеть SPECTER-модели.
    """

    # Persist isolated paper metadata required by the global embedding foreign key.
    database = Database(Settings())
    candidate = Paper(id=uuid4(), title="Graph neural retrieval", abstract="Vector search")
    seed = Paper(id=uuid4(), title="Scientific document retrieval")
    question = ResearchQuestion(project_id=uuid4(), text="How are papers retrieved?")
    paper_ids = {candidate.id, seed.id}
    try:
        with database.session_factory() as session:
            session.add_all(
                [
                    PaperModel(
                        id=paper.id,
                        title=paper.title,
                        abstract=paper.abstract,
                        authors=[],
                        categories=[],
                    )
                    for paper in [candidate, seed]
                ]
            )
            session.commit()

            # Run the complete service with the real model and pgvector repository.
            embedding_service = EmbeddingService(
                "sentence-transformers/allenai-specter",
                "phase-2-integration",
                768,
                2,
            )
            repository = EmbeddingRepository(session)
            result = PreliminaryScoringService(
                embedding_service,
                repository,
                PreliminarySemanticScorer(0.7, 0.3),
            ).rank([candidate], [seed], [question], 1)
            session.commit()
            first_read = repository.get_many(
                paper_ids,
                embedding_service.model_name,
                embedding_service.model_version,
                embedding_service.dimensions,
            )
            session.expire_all()
            second_read = EmbeddingRepository(session).get_many(
                paper_ids,
                embedding_service.model_name,
                embedding_service.model_version,
                embedding_service.dimensions,
            )

            assert len(result.shortlists) == 1
            assert len(first_read) == len(second_read) == 2
            assert {embedding.paper_id for embedding in second_read} == paper_ids
            assert all(len(embedding.vector) == 768 for embedding in second_read)
            assert all(
                sqrt(sum(value * value for value in embedding.vector)) == pytest.approx(1.0)
                for embedding in second_read
            )
            first_vectors = {embedding.paper_id: embedding.vector for embedding in first_read}
            assert all(
                embedding.vector == pytest.approx(first_vectors[embedding.paper_id])
                for embedding in second_read
            )
    finally:
        # Remove only rows created by this integration test.
        with database.session_factory() as session:
            session.execute(
                delete(PaperEmbeddingModel).where(PaperEmbeddingModel.paper_id.in_(paper_ids))
            )
            session.execute(delete(PaperModel).where(PaperModel.id.in_(paper_ids)))
            session.commit()
        database.dispose()
