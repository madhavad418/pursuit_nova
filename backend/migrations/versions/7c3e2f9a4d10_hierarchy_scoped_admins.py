"""Hierarchy-scoped admins: roles.created_by and Admin/Director moved to team scope

Only Super Admins keep organisation-wide visibility. Roles an Admin creates are
owned by that Admin's organisation via roles.created_by (NULL = shared role).

Revision ID: 7c3e2f9a4d10
Revises: 51b7a9c1e201
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '7c3e2f9a4d10'
down_revision: Union[str, None] = '51b7a9c1e201'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('roles', sa.Column('created_by', sa.Integer(), nullable=True))
    op.execute("UPDATE roles SET scope_type = 'team' WHERE name IN ('Admin', 'Director') AND scope_type = 'all'")


def downgrade() -> None:
    op.execute("UPDATE roles SET scope_type = 'all' WHERE name IN ('Admin', 'Director') AND scope_type = 'team'")
    op.drop_column('roles', 'created_by')
