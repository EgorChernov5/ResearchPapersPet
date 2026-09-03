from dataclasses import asdict
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.paper import Paper
from app.domain.project import ResearchConfig, ResearchProject, ResearchQuestion
from app.domain.related_work import PaperIdentityInput, RelatedWorkEntry
from app.infrastructure.models import (
    PaperModel,
    ProjectPaperModel,
    RelatedWorkEntryModel,
    ResearchProjectModel,
    ResearchQuestionModel,
)


class ProjectRepository:
    """
    Читает project configuration и seed identities для pipeline.

    Attributes:
        session (Session): Текущая SQLAlchemy session.

    Fallbacks:
        Missing project возвращает None и обрабатывается application layer.
    """

    def __init__(self, session: Session) -> None:
        """
        Создаёт project repository.

        Parameters:
            session (Session): SQLAlchemy session.

        Returns:
            None: Метод сохраняет session.

        Fallbacks:
            Repository не управляет transaction lifecycle.
        """

        self.session = session

    def create(self, name: str, config: ResearchConfig) -> ResearchProject:
        """
        Создаёт новый research project.

        Parameters:
            name (str): Пользовательское имя проекта.
            config (ResearchConfig): Проверенная project configuration.

        Returns:
            ResearchProject: Созданная domain entity.

        Fallbacks:
            Пустое имя или invalid config отклоняются domain validation.
        """

        project = ResearchProject(name=name, config=config)
        model = ResearchProjectModel(
            id=project.id,
            name=project.name,
            config=asdict(project.config),
        )
        self.session.add(model)
        self.session.flush()
        return project

    def get(self, project_id: UUID) -> ResearchProject | None:
        """
        Загружает project вместе с research questions.

        Parameters:
            project_id (UUID): Идентификатор проекта.

        Returns:
            ResearchProject | None: Domain project или None.

        Fallbacks:
            Missing project не создаёт exception.
        """

        model = self.session.get(ResearchProjectModel, project_id)
        if model is None:
            return None
        questions = self.get_questions(project_id)
        return ResearchProject(
            id=model.id,
            name=model.name,
            config=ResearchConfig(**(model.config or {})),
            questions=questions,
        )

    def add_questions(self, project_id: UUID, texts: list[str]) -> list[ResearchQuestion]:
        """
        Добавляет несколько research questions к проекту.

        Parameters:
            project_id (UUID): Идентификатор проекта.
            texts (list[str]): Непустые тексты вопросов.

        Returns:
            list[ResearchQuestion]: Созданные domain questions.

        Fallbacks:
            Missing project или пустой текст отклоняются до commit.
        """

        if self.session.get(ResearchProjectModel, project_id) is None:
            raise ValueError(f"Research project {project_id} was not found")
        questions = [ResearchQuestion(project_id=project_id, text=text) for text in texts]
        for question in questions:
            self.session.add(
                ResearchQuestionModel(
                    id=question.id,
                    project_id=question.project_id,
                    text=question.text,
                )
            )
        self.session.flush()
        return questions

    def replace_related_work(
        self,
        project_id: UUID,
        entries: list[RelatedWorkEntry],
    ) -> list[RelatedWorkEntry]:
        """
        Заменяет Related Work entries одного проекта результатом нового upload.

        Parameters:
            project_id (UUID): Идентификатор проекта.
            entries (list[RelatedWorkEntry]): Проверенные parser entries.

        Returns:
            list[RelatedWorkEntry]: Сохранённые entries.

        Fallbacks:
            Missing project отклоняется; parser гарантирует непустой список.
        """

        if self.session.get(ResearchProjectModel, project_id) is None:
            raise ValueError(f"Research project {project_id} was not found")

        # Replace only project-scoped annotations while retaining global scientific data.
        self.session.execute(
            delete(RelatedWorkEntryModel).where(RelatedWorkEntryModel.project_id == project_id)
        )
        for entry in entries:
            self.session.add(
                RelatedWorkEntryModel(
                    project_id=project_id,
                    local_id=entry.local_id,
                    title=entry.title,
                    year=entry.year,
                    source=entry.source,
                    venue=entry.venue,
                    bibtex_key=entry.bibtex_key,
                    literature_block=entry.literature_block,
                    task=entry.task,
                    method=entry.method,
                    datasets=entry.datasets,
                    metrics=entry.metrics,
                    code_available=entry.code_available,
                    data_available=entry.data_available,
                    usefulness=entry.usefulness,
                    comparison_ideas=entry.comparison_ideas,
                )
            )
        self.session.flush()
        return entries

    def get_config(self, project_id: UUID) -> ResearchConfig | None:
        """
        Загружает research config проекта.

        Parameters:
            project_id (UUID): Идентификатор проекта.

        Returns:
            ResearchConfig | None: Доменная конфигурация или None.

        Fallbacks:
            Пустой JSON использует defaults ResearchConfig.
        """

        model = self.session.get(ResearchProjectModel, project_id)
        if model is None:
            return None
        return ResearchConfig(**(model.config or {}))

    def get_seed_identities(self, project_id: UUID) -> list[PaperIdentityInput]:
        """
        Загружает минимальные resolver inputs из Related Work.

        Parameters:
            project_id (UUID): Идентификатор проекта.

        Returns:
            list[PaperIdentityInput]: Seeds в стабильном local_id порядке.

        Fallbacks:
            Проект без Related Work возвращает пустой список.
        """

        models = self.session.scalars(
            select(RelatedWorkEntryModel)
            .where(RelatedWorkEntryModel.project_id == project_id)
            .order_by(RelatedWorkEntryModel.local_id)
        )
        return [
            PaperIdentityInput(
                local_id=model.local_id,
                title=model.title,
                year=model.year,
                source=model.source,
            )
            for model in models
        ]

    def get_questions(self, project_id: UUID) -> list[ResearchQuestion]:
        """
        Загружает research questions проекта в stable order.

        Parameters:
            project_id (UUID): Идентификатор проекта.

        Returns:
            list[ResearchQuestion]: Domain questions.

        Fallbacks:
            Проект без вопросов возвращает пустой список.
        """

        models = self.session.scalars(
            select(ResearchQuestionModel)
            .where(ResearchQuestionModel.project_id == project_id)
            .order_by(ResearchQuestionModel.id)
        )
        return [
            ResearchQuestion(id=model.id, project_id=model.project_id, text=model.text)
            for model in models
        ]

    def get_papers(self, project_id: UUID) -> list[Paper]:
        """
        Загружает глобальные papers, прикреплённые к проекту.

        Parameters:
            project_id (UUID): Идентификатор проекта.

        Returns:
            list[Paper]: Domain papers в depth/title order.

        Fallbacks:
            Проект без discovery result возвращает пустой список.
        """

        models = self.session.scalars(
            select(PaperModel)
            .join(ProjectPaperModel, ProjectPaperModel.paper_id == PaperModel.id)
            .where(ProjectPaperModel.project_id == project_id)
            .order_by(ProjectPaperModel.depth, PaperModel.title)
        )
        return [
            Paper(
                id=model.id,
                semantic_scholar_id=model.semantic_scholar_id,
                title=model.title,
                abstract=model.abstract,
                year=model.year,
                citation_count=model.citation_count,
                influential_citation_count=model.influential_citation_count,
                reference_count=model.reference_count,
                authors=list(model.authors),
                categories=list(model.categories),
                pdf_url=model.pdf_url,
            )
            for model in models
        ]

    def get_seed_paper_ids(self, project_id: UUID) -> set[UUID]:
        """
        Загружает global IDs seed papers проекта.

        Parameters:
            project_id (UUID): Идентификатор проекта.

        Returns:
            set[UUID]: Идентификаторы seeds.

        Fallbacks:
            Проект без resolved seeds возвращает пустое множество.
        """

        return set(
            self.session.scalars(
                select(ProjectPaperModel.paper_id).where(
                    ProjectPaperModel.project_id == project_id,
                    ProjectPaperModel.is_seed.is_(True),
                )
            )
        )
