"""Add document domain, processing jobs, parsed elements and chunks.

Revision ID: 20260929_0003
Revises: 20260825_0002
Create Date: 2026-09-29
"""

import sqlalchemy as sa
from alembic import op

revision = "20260929_0003"
down_revision = "20260825_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Создаёт persistence schema независимого document pipeline.

    Returns:
        None: Схема обновляется до document revision.

    Fallbacks:
        Alembic transaction откатывает все DDL при ошибке.
    """

    # Create global PDF versions with one active document per paper/source pair.
    op.create_table(
        "paper_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("media_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_paper_documents_positive_version"),
        sa.CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="ck_paper_documents_non_negative_size",
        ),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id", "source", "version"),
    )
    op.create_index(
        op.f("ix_paper_documents_paper_id"),
        "paper_documents",
        ["paper_id"],
    )
    op.create_index(
        "uq_paper_documents_active_source",
        "paper_documents",
        ["paper_id", "source"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    # Keep project target ownership separate from global reusable document artifacts.
    op.create_table(
        "document_processing_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("research_job_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["paper_documents.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["research_projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_job_id"],
            ["research_jobs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "paper_id", "source"),
    )
    for column in ["document_id", "paper_id", "project_id", "research_job_id"]:
        op.create_index(
            op.f(f"ix_document_processing_jobs_{column}"),
            "document_processing_jobs",
            [column],
        )

    # Store each parser version once for a PDF and cascade normalized content with it.
    op.create_table(
        "parsed_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("parser_name", sa.String(length=100), nullable=False),
        sa.Column("parser_version", sa.String(length=100), nullable=False),
        sa.Column("tei_storage_key", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["paper_documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "parser_name", "parser_version"),
    )
    op.create_index(
        op.f("ix_parsed_documents_document_id"),
        "parsed_documents",
        ["document_id"],
    )
    op.create_table(
        "document_elements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("parsed_document_id", sa.Uuid(), nullable=False),
        sa.Column("element_type", sa.String(length=50), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("section_path", sa.JSON(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("coordinates", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_document_elements_non_negative_position",
        ),
        sa.ForeignKeyConstraint(
            ["parsed_document_id"],
            ["parsed_documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("parsed_document_id", "position"),
    )
    op.create_index(
        op.f("ix_document_elements_parsed_document_id"),
        "document_elements",
        ["parsed_document_id"],
    )
    op.create_table(
        "citation_markers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("marker_element_id", sa.Uuid(), nullable=False),
        sa.Column("bibliography_element_id", sa.Uuid(), nullable=False),
        sa.Column("marker_text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["bibliography_element_id"],
            ["document_elements.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["marker_element_id"],
            ["document_elements.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("marker_element_id", "bibliography_element_id"),
    )
    op.create_index(
        op.f("ix_citation_markers_bibliography_element_id"),
        "citation_markers",
        ["bibliography_element_id"],
    )
    op.create_index(
        op.f("ix_citation_markers_marker_element_id"),
        "citation_markers",
        ["marker_element_id"],
    )

    # Keep canonical chunk text/version metadata in PostgreSQL before Qdrant indexing exists.
    op.create_table(
        "paper_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("parsed_document_id", sa.Uuid(), nullable=False),
        sa.Column("element_id", sa.Uuid(), nullable=True),
        sa.Column("stable_id", sa.String(length=255), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_start", sa.Integer(), nullable=False),
        sa.Column("token_end", sa.Integer(), nullable=False),
        sa.Column("section_path", sa.JSON(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("coordinates", sa.JSON(), nullable=True),
        sa.Column("chunker_version", sa.String(length=100), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("embedding_version", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("chunk_index >= 0", name="ck_paper_chunks_non_negative_index"),
        sa.CheckConstraint(
            "token_start >= 0 AND token_end >= token_start",
            name="ck_paper_chunks_token_offsets",
        ),
        sa.ForeignKeyConstraint(
            ["element_id"],
            ["document_elements.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["parsed_document_id"],
            ["parsed_documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("parsed_document_id", "chunker_version", "chunk_index"),
        sa.UniqueConstraint("stable_id"),
    )
    op.create_index(op.f("ix_paper_chunks_element_id"), "paper_chunks", ["element_id"])
    op.create_index(
        op.f("ix_paper_chunks_parsed_document_id"),
        "paper_chunks",
        ["parsed_document_id"],
    )
    op.create_index(
        "uq_paper_chunks_active_position",
        "paper_chunks",
        ["parsed_document_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    """
    Удаляет document pipeline schema в обратном dependency порядке.

    Returns:
        None: Схема возвращается к semantic-ranking revision.

    Fallbacks:
        Alembic transaction не оставляет частично удалённые таблицы.
    """

    # Drop derived content before jobs and global PDF versions.
    op.drop_index("uq_paper_chunks_active_position", table_name="paper_chunks")
    op.drop_index(op.f("ix_paper_chunks_parsed_document_id"), table_name="paper_chunks")
    op.drop_index(op.f("ix_paper_chunks_element_id"), table_name="paper_chunks")
    op.drop_table("paper_chunks")
    op.drop_index(
        op.f("ix_citation_markers_marker_element_id"),
        table_name="citation_markers",
    )
    op.drop_index(
        op.f("ix_citation_markers_bibliography_element_id"),
        table_name="citation_markers",
    )
    op.drop_table("citation_markers")
    op.drop_index(
        op.f("ix_document_elements_parsed_document_id"),
        table_name="document_elements",
    )
    op.drop_table("document_elements")
    op.drop_index(
        op.f("ix_parsed_documents_document_id"),
        table_name="parsed_documents",
    )
    op.drop_table("parsed_documents")
    for column in ["research_job_id", "project_id", "paper_id", "document_id"]:
        op.drop_index(
            op.f(f"ix_document_processing_jobs_{column}"),
            table_name="document_processing_jobs",
        )
    op.drop_table("document_processing_jobs")
    op.drop_index("uq_paper_documents_active_source", table_name="paper_documents")
    op.drop_index(op.f("ix_paper_documents_paper_id"), table_name="paper_documents")
    op.drop_table("paper_documents")
