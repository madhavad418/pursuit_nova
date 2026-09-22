"""Add admin_reply to actions and generic_actions

Revision ID: d9f5e3a06c72
Revises: c4b8e2f5a913
Create Date: 2026-09-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd9f5e3a06c72'
down_revision: Union[str, None] = 'c4b8e2f5a913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Nullable, so every existing row keeps its current values untouched
    op.add_column('actions', sa.Column('admin_reply', sa.Text(), nullable=True))
    op.add_column('generic_actions', sa.Column('admin_reply', sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column('generic_actions', 'admin_reply')
    op.drop_column('actions', 'admin_reply')
