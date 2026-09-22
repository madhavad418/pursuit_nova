"""Add post_overdue_date to actions and generic_actions

Revision ID: b8e4d2f05c61
Revises: a7f3c1d92b40
Create Date: 2026-09-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b8e4d2f05c61'
down_revision: Union[str, None] = 'a7f3c1d92b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Nullable, so every existing row keeps its current values untouched
    op.add_column('actions', sa.Column('post_overdue_date', sa.String(10), nullable=True))
    op.add_column('generic_actions', sa.Column('post_overdue_date', sa.String(10), nullable=True))

def downgrade() -> None:
    op.drop_column('generic_actions', 'post_overdue_date')
    op.drop_column('actions', 'post_overdue_date')
