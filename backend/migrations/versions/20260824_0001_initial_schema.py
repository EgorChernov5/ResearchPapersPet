"""Create the initial research graph schema.

Revision ID: 20260824_0001
Revises: None
Create Date: 2026-08-24
"""

import sqlalchemy as sa
from alembic import op

revision = "20260824_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Создаёт таблицы foundation-этапа.

    Returns:
        None: Схема PostgreSQL обновляется до initial revision.

    Fallbacks:
        Транзакция Alembic откатывается при любой ошибке DDL.
    """

    # Create project-owned tables before their dependent rows.
    op.create_table(
        "research_projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "research_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_research_questions_project_id"),
        "research_questions",
        ["project_id"],
    )
    op.create_table(
        "related_work_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("local_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("venue", sa.String(length=255), nullable=True),
        sa.Column("bibtex_key", sa.String(length=255), nullable=True),
        sa.Column("literature_block", sa.Text(), nullable=True),
        sa.Column("task", sa.Text(), nullable=True),
        sa.Column("method", sa.Text(), nullable=True),
        sa.Column("datasets", sa.Text(), nullable=True),
        sa.Column("metrics", sa.Text(), nullable=True),
        sa.Column("code_available", sa.String(length=100), nullable=True),
        sa.Column("data_available", sa.String(length=100), nullable=True),
        sa.Column("usefulness", sa.Text(), nullable=True),
        sa.Column("comparison_ideas", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "local_id"),
    )
    op.create_index(
        op.f("ix_related_work_entries_project_id"),
        "related_work_entries",
        ["project_id"],
    )

    # Create globally shared scientific entities and unique citation edges.
    op.create_table(
        "papers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("semantic_scholar_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("citation_count", sa.Integer(), nullable=True),
        sa.Column("influential_citation_count", sa.Integer(), nullable=True),
        sa.Column("reference_count", sa.Integer(), nullable=True),
        sa.Column("authors", sa.JSON(), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("pdf_url", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_papers_semantic_scholar_id"),
        "papers",
        ["semantic_scholar_id"],
        unique=True,
    )
    op.create_table(
        "external_identifiers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id", "provider"),
        sa.UniqueConstraint("provider", "value"),
    )
    op.create_index(
        op.f("ix_external_identifiers_paper_id"),
        "external_identifiers",
        ["paper_id"],
    )
    op.create_table(
        "citations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_paper_id", sa.Uuid(), nullable=False),
        sa.Column("target_paper_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["source_paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_paper_id", "target_paper_id"),
    )
    op.create_index(op.f("ix_citations_source_paper_id"), "citations", ["source_paper_id"])
    op.create_index(op.f("ix_citations_target_paper_id"), "citations", ["target_paper_id"])

    # Create project associations and background job state last.
    op.create_table(
        "project_papers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("is_seed", sa.Boolean(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=True),
        sa.Column("query_similarity", sa.Float(), nullable=True),
        sa.Column("seed_similarity", sa.Float(), nullable=True),
        sa.Column("topic_score", sa.Float(), nullable=True),
        sa.Column("citation_score", sa.Float(), nullable=True),
        sa.Column("recency_score", sa.Float(), nullable=True),
        sa.Column("impact_score", sa.Float(), nullable=True),
        sa.Column("distance_score", sa.Float(), nullable=True),
        sa.Column("connectivity_score", sa.Float(), nullable=True),
        sa.Column("pagerank_score", sa.Float(), nullable=True),
        sa.Column("graph_score", sa.Float(), nullable=True),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "paper_id"),
    )
    op.create_index(op.f("ix_project_papers_paper_id"), "project_papers", ["paper_id"])
    op.create_index(op.f("ix_project_papers_project_id"), "project_papers", ["project_id"])
    op.create_table(
        "research_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("papers_discovered", sa.Integer(), nullable=False),
        sa.Column("papers_processed", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_research_jobs_project_id"), "research_jobs", ["project_id"])


def downgrade() -> None:
    """
    Удаляет таблицы foundation-этапа в безопасном порядке зависимостей.

    Returns:
        None: Схема возвращается к состоянию до initial revision.

    Fallbacks:
        Транзакция Alembic откатывается при любой ошибке DDL.
    """

    # Drop dependent project tables before their parents.
    op.drop_index(op.f("ix_research_jobs_project_id"), table_name="research_jobs")
    op.drop_table("research_jobs")
    op.drop_index(op.f("ix_project_papers_project_id"), table_name="project_papers")
    op.drop_index(op.f("ix_project_papers_paper_id"), table_name="project_papers")
    op.drop_table("project_papers")
    op.drop_index(op.f("ix_citations_target_paper_id"), table_name="citations")
    op.drop_index(op.f("ix_citations_source_paper_id"), table_name="citations")
    op.drop_table("citations")
    op.drop_index(op.f("ix_external_identifiers_paper_id"), table_name="external_identifiers")
    op.drop_table("external_identifiers")
    op.drop_index(op.f("ix_papers_semantic_scholar_id"), table_name="papers")
    op.drop_table("papers")
    op.drop_index(op.f("ix_related_work_entries_project_id"), table_name="related_work_entries")
    op.drop_table("related_work_entries")
    op.drop_index(op.f("ix_research_questions_project_id"), table_name="research_questions")
    op.drop_table("research_questions")
    op.drop_table("research_projects")
