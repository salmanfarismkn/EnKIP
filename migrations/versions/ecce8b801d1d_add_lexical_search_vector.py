"""add lexical search vector

Revision ID: ecce8b801d1d
Revises: 5e2acdd7acb3
Create Date: 2026-09-28 18:26:11.246368

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ecce8b801d1d'
down_revision: Union[str, Sequence[str], None] = '5e2acdd7acb3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            nullable=True,
        ),
    )

    op.execute(
        """
        UPDATE document_chunks
        SET search_vector =
            to_tsvector(
                'english',
                coalesce(text, '')
            )
        """
    )

    op.execute(
        """
        CREATE INDEX ix_document_chunks_search_vector
        ON document_chunks
        USING GIN (search_vector)
        """
    )

    op.execute(
        """
        CREATE FUNCTION document_chunks_search_vector_update()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.search_vector :=
                to_tsvector(
                    'english',
                    coalesce(NEW.text, '')
                );

            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE TRIGGER document_chunks_search_vector_trigger
        BEFORE INSERT OR UPDATE OF text
        ON document_chunks
        FOR EACH ROW
        EXECUTE FUNCTION
        document_chunks_search_vector_update()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS
        document_chunks_search_vector_trigger
        ON document_chunks
        """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS
        document_chunks_search_vector_update()
        """
    )

    op.drop_index(
        "ix_document_chunks_search_vector",
        table_name="document_chunks",
    )

    op.drop_column(
        "document_chunks",
        "search_vector",
    )