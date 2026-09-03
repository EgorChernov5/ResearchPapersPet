from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.citation import Citation
from app.infrastructure.models import CitationModel


class CitationRepository:
    """
    Сохраняет уникальные глобальные citation edges.

    Attributes:
        session (Session): Текущая SQLAlchemy transaction session.

    Fallbacks:
        Duplicate и self edges не создают новые строки.
    """

    def __init__(self, session: Session) -> None:
        """
        Создаёт repository внутри существующей transaction boundary.

        Parameters:
            session (Session): SQLAlchemy session.

        Returns:
            None: Метод сохраняет session.

        Fallbacks:
            Commit и rollback выполняет application layer.
        """

        self.session = session

    def upsert(
        self,
        source_paper_id: UUID,
        target_paper_id: UUID,
    ) -> Citation | None:
        """
        Сохраняет edge по правилу source cites target.

        Parameters:
            source_paper_id (UUID): Цитирующая global Paper.
            target_paper_id (UUID): Цитируемая global Paper.

        Returns:
            Citation | None: Сохранённое edge или None для self edge.

        Fallbacks:
            Existing edge возвращается без duplicate INSERT.
        """

        if source_paper_id == target_paper_id:
            return None
        model = self.session.scalar(
            select(CitationModel).where(
                CitationModel.source_paper_id == source_paper_id,
                CitationModel.target_paper_id == target_paper_id,
            )
        )
        if model is None:
            model = CitationModel(
                source_paper_id=source_paper_id,
                target_paper_id=target_paper_id,
            )
            self.session.add(model)
            self.session.flush()
        return Citation(
            id=model.id,
            source_paper_id=model.source_paper_id,
            target_paper_id=model.target_paper_id,
        )

    def get_for_papers(self, paper_ids: set[UUID]) -> list[Citation]:
        """
        Загружает edges, у которых обе стороны входят в project paper set.

        Parameters:
            paper_ids (set[UUID]): Идентификаторы project papers.

        Returns:
            list[Citation]: Directed project subgraph edges.

        Fallbacks:
            Пустой paper set возвращает пустой список без SQL query.
        """

        if not paper_ids:
            return []
        models = self.session.scalars(
            select(CitationModel)
            .where(
                CitationModel.source_paper_id.in_(paper_ids),
                CitationModel.target_paper_id.in_(paper_ids),
            )
            .order_by(CitationModel.source_paper_id, CitationModel.target_paper_id)
        )
        return [
            Citation(
                id=model.id,
                source_paper_id=model.source_paper_id,
                target_paper_id=model.target_paper_id,
            )
            for model in models
        ]
