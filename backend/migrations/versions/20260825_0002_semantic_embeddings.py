"""Add pgvector embeddings and per-question semantic scores.

Revision ID: 20260825_0002
Revises: 20260824_0001
Create Date: 2026-08-25
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision = "20260825_0002"
down_revision = "20260824_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Включает pgvector и создаёт semantic persistence tables.

    Returns:
        None: Схема обновляется до semantic-ranking revision.

    Fallbacks:
        Alembic transaction откатывает DDL при недоступном vector extension.
    """

    # Enable vector storage once for the current research database.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "paper_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding", VECTOR(768), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id", "model_name", "model_version"),
    )
    op.create_index(
        op.f("ix_paper_embeddings_paper_id"),
        "paper_embeddings",
        ["paper_id"],
    )

    # Preserve paper × question scores before max project aggregation.
    op.create_table(
        "project_paper_question_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("query_similarity", sa.Float(), nullable=True),
        sa.Column("topic_score", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["research_questions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "paper_id", "question_id"),
    )
    op.create_index(
        op.f("ix_project_paper_question_scores_project_id"),
        "project_paper_question_scores",
        ["project_id"],
    )
    op.create_index(
        op.f("ix_project_paper_question_scores_paper_id"),
        "project_paper_question_scores",
        ["paper_id"],
    )
    op.create_index(
        op.f("ix_project_paper_question_scores_question_id"),
        "project_paper_question_scores",
        ["question_id"],
    )


def downgrade() -> None:
    """
    Удаляет semantic persistence tables без удаления shared extension.

    Returns:
        None: Схема возвращается к foundation revision.

    Fallbacks:
        Vector extension остаётся доступным другим database objects.
    """

    # Drop dependent semantic score indexes and table first.
    op.drop_index(
        op.f("ix_project_paper_question_scores_question_id"),
        table_name="project_paper_question_scores",
    )
    op.drop_index(
        op.f("ix_project_paper_question_scores_paper_id"),
        table_name="project_paper_question_scores",
    )
    op.drop_index(
        op.f("ix_project_paper_question_scores_project_id"),
        table_name="project_paper_question_scores",
    )
    op.drop_table("project_paper_question_scores")
    op.drop_index(op.f("ix_paper_embeddings_paper_id"), table_name="paper_embeddings")
    op.drop_table("paper_embeddings")
