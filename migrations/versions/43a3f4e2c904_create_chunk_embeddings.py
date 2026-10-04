"""create chunk embeddings table

Revision ID: 43a3f4e2c904
Revises: fbe42262eb18
Create Date: 2026-10-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = "43a3f4e2c904"
down_revision: Union[str, Sequence[str], None] = "fbe42262eb18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chunk_embeddings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=255), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"], ["document_chunks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chunk_embeddings_chunk_id",
        "chunk_embeddings",
        ["chunk_id"],
        unique=False,
    )
    op.create_index(
        "ix_chunk_embeddings_tenant_id",
        "chunk_embeddings",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chunk_embeddings_tenant_id",
        table_name="chunk_embeddings",
    )
    op.drop_index(
        "ix_chunk_embeddings_chunk_id",
        table_name="chunk_embeddings",
    )
    op.drop_table("chunk_embeddings")