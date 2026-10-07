"""Add a default deal currency to each prospect (leads.currency)

Revision ID: e1a7c4b2d9f0
Revises: d9f5e3a06c72
Create Date: 2026-10-07
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e1a7c4b2d9f0'
down_revision: Union[str, None] = 'd9f5e3a06c72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable so the ALTER is instant and existing rows are untouched by the DDL...
    op.add_column('leads', sa.Column('currency', sa.String(length=10), nullable=True))
    # ...then every prospect gets a default from its region (corporate currency when unmapped),
    # so the Prospects table never shows a blank and new opportunities always have a pre-fill.
    from app.db import backfill_lead_currency
    backfill_lead_currency(op.get_bind())


def downgrade() -> None:
    op.drop_column('leads', 'currency')
