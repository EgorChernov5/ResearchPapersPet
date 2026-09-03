from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.embedding import EmbeddedPaper
from app.infrastructure.models import PaperEmbeddingModel


class EmbeddingRepository:
    """
    Кэширует versioned global paper embeddings через pgvector.

    Attributes:
        session (Session): Текущая SQLAlchemy transaction session.

    Fallbacks:
        Model/version/dimension mismatch исключает несовместимый cached vector.
    """

    def __init__(self, session: Session) -> None:
        """
        Создаёт embedding repository.

        Parameters:
            session (Session): SQLAlchemy session.

        Returns:
            None: Метод сохраняет session.

        Fallbacks:
            Transaction lifecycle остаётся application responsibility.
        """

        self.session = session

    def get_many(
        self,
        paper_ids: set[UUID],
        model_name: str,
        model_version: str,
        dimensions: int,
    ) -> list[EmbeddedPaper]:
        """
        Загружает cached embeddings указанной model version.

        Parameters:
            paper_ids (set[UUID]): Global paper IDs.
            model_name (str): Embedding model identifier.
            model_version (str): Persistence version.
            dimensions (int): Required vector dimensions.

        Returns:
            list[EmbeddedPaper]: Найденные cached vectors.

        Fallbacks:
            Пустой input возвращает пустой список без SQL query.
        """

        if not paper_ids:
            return []
        models = self.session.scalars(
            select(PaperEmbeddingModel).where(
                PaperEmbeddingModel.paper_id.in_(paper_ids),
                PaperEmbeddingModel.model_name == model_name,
                PaperEmbeddingModel.model_version == model_version,
                PaperEmbeddingModel.dimensions == dimensions,
            )
        )
        return [
            EmbeddedPaper(
                paper_id=model.paper_id,
                vector=(
                    model.embedding.tolist()
                    if hasattr(model.embedding, "tolist")
                    else list(model.embedding)
                ),
            )
            for model in models
        ]

    def upsert(
        self,
        embedding: EmbeddedPaper,
        model_name: str,
        model_version: str,
        dimensions: int,
    ) -> EmbeddedPaper:
        """
        Создаёт или обновляет versioned paper embedding.

        Parameters:
            embedding (EmbeddedPaper): Paper ID и vector.
            model_name (str): Embedding model identifier.
            model_version (str): Persistence version.
            dimensions (int): Ожидаемая размерность.

        Returns:
            EmbeddedPaper: Сохранённый domain embedding.

        Fallbacks:
            Dimension mismatch отклоняется до database flush.
        """

        if len(embedding.vector) != dimensions:
            raise ValueError(
                f"Embedding for paper {embedding.paper_id} has {len(embedding.vector)} "
                f"dimensions; expected {dimensions}"
            )
        model = self.session.scalar(
            select(PaperEmbeddingModel).where(
                PaperEmbeddingModel.paper_id == embedding.paper_id,
                PaperEmbeddingModel.model_name == model_name,
                PaperEmbeddingModel.model_version == model_version,
            )
        )
        if model is None:
            model = PaperEmbeddingModel(
                paper_id=embedding.paper_id,
                model_name=model_name,
                model_version=model_version,
                dimensions=dimensions,
                embedding=embedding.vector,
            )
            self.session.add(model)
        else:
            model.dimensions = dimensions
            model.embedding = embedding.vector
        self.session.flush()
        return embedding
