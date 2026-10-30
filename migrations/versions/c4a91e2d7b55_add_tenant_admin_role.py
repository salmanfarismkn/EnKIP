"""add tenant administrator role

Revision ID: c4a91e2d7b55
Revises: 7f4c2a9e1b6d
Create Date: 2026-10-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4a91e2d7b55"
down_revision: Union[str, Sequence[str], None] = "7f4c2a9e1b6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_tenant_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_tenant_admin")
