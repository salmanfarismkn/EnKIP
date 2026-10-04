"""restore lexical search GIN index

Revision ID: a8fd8271c5d9
Revises: 9fdbadce35c6
Create Date: 2026-10-04

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a8fd8271c5d9"
down_revision: Union[str, Sequence[str], None] = "9fdbadce35c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_search_vector
        ON document_chunks
        USING GIN (search_vector)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_document_chunks_search_vector
        """
    )