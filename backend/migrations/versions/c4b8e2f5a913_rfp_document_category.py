"""RFP document category (description / technical response sub-tabs)

Revision ID: c4b8e2f5a913
Revises: a7f3c1d92b40
Create Date: 2026-09-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c4b8e2f5a913'
down_revision: Union[str, None] = 'b8e4d2f05c61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('rfp_documents', sa.Column('category', sa.String(30), nullable=False, server_default='general'))

def downgrade() -> None:
    op.drop_column('rfp_documents', 'category')
