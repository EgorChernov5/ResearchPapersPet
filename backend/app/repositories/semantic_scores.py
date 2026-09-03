from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.scoring import ProjectPaperQuestionScore
from app.infrastructure.models import ProjectPaperQuestionScoreModel


class SemanticScoreRepository:
    """
    Сохраняет paper × question semantic scores idempotently.

    Attributes:
        session (Session): Текущая SQLAlchemy transaction session.

    Fallbacks:
        Repeated scoring обновляет существующую строку.
    """

    def __init__(self, session: Session) -> None:
        """
        Создаёт semantic score repository.

        Parameters:
            session (Session): SQLAlchemy session.

        Returns:
            None: Метод сохраняет session.

        Fallbacks:
            Commit выполняет application layer.
        """

        self.session = session

    def upsert(
        self,
        score: ProjectPaperQuestionScore,
    ) -> ProjectPaperQuestionScore:
        """
        Сохраняет similarity и topic score одной пары.

        Parameters:
            score (ProjectPaperQuestionScore): Pair-level score DTO.

        Returns:
            ProjectPaperQuestionScore: Сохранённый DTO.

        Fallbacks:
            Missing values сохраняются как NULL, а не zero.
        """

        model = self.session.scalar(
            select(ProjectPaperQuestionScoreModel).where(
                ProjectPaperQuestionScoreModel.project_id == score.project_id,
                ProjectPaperQuestionScoreModel.paper_id == score.paper_id,
                ProjectPaperQuestionScoreModel.question_id == score.question_id,
            )
        )
        if model is None:
            model = ProjectPaperQuestionScoreModel(
                project_id=score.project_id,
                paper_id=score.paper_id,
                question_id=score.question_id,
            )
            self.session.add(model)
        model.query_similarity = score.query_similarity
        model.topic_score = score.topic_score
        self.session.flush()
        return score

    def get_for_paper(
        self,
        project_id: UUID,
        paper_id: UUID,
    ) -> list[ProjectPaperQuestionScore]:
        """
        Загружает semantic scores статьи по всем research questions.

        Parameters:
            project_id (UUID): Идентификатор проекта.
            paper_id (UUID): Идентификатор global paper.

        Returns:
            list[ProjectPaperQuestionScore]: Pair-level scores по question ID.

        Fallbacks:
            Paper без рассчитанных scores возвращает пустой список.
        """

        models = self.session.scalars(
            select(ProjectPaperQuestionScoreModel)
            .where(
                ProjectPaperQuestionScoreModel.project_id == project_id,
                ProjectPaperQuestionScoreModel.paper_id == paper_id,
            )
            .order_by(ProjectPaperQuestionScoreModel.question_id)
        )
        return [
            ProjectPaperQuestionScore(
                project_id=model.project_id,
                paper_id=model.paper_id,
                question_id=model.question_id,
                query_similarity=model.query_similarity,
                topic_score=model.topic_score,
            )
            for model in models
        ]
