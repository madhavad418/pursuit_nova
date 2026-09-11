"""PursuitNova v5.1 enterprise controls

Revision ID: 51b7a9c1e201
Revises: 36fd817b596a
Create Date: 2026-09-11
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '51b7a9c1e201'
down_revision: Union[str, None] = '36fd817b596a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table('org_settings',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('key',sa.String(120),nullable=False,unique=True),
        sa.Column('value',sa.Text(),nullable=False),
        sa.Column('updated_by',sa.Integer(),sa.ForeignKey('users.id')),
        sa.Column('updated_at',sa.DateTime(),server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_table('fx_rates',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('currency',sa.String(10),nullable=False,unique=True),
        sa.Column('rate_to_corporate',sa.Float(),nullable=False),
        sa.Column('as_of',sa.String(10),nullable=False),
        sa.Column('source',sa.String(120),nullable=False),
        sa.Column('updated_by',sa.Integer(),sa.ForeignKey('users.id')),
        sa.Column('updated_at',sa.DateTime(),server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_table('field_permissions',
        sa.Column('role_id',sa.Integer(),sa.ForeignKey('roles.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('entity_type',sa.String(40),primary_key=True),
        sa.Column('field_name',sa.String(80),primary_key=True),
        sa.Column('can_view',sa.Boolean(),nullable=False),
        sa.Column('can_edit',sa.Boolean(),nullable=False),
    )
    op.create_table('saved_views',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('module',sa.String(40),nullable=False),
        sa.Column('name',sa.String(160),nullable=False),
        sa.Column('filters_json',sa.Text(),nullable=False),
        sa.Column('columns_json',sa.Text(),nullable=False),
        sa.Column('is_default',sa.Boolean(),nullable=False),
        sa.Column('created_at',sa.DateTime(),server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at',sa.DateTime(),server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('user_id','module','name',name='uq_saved_view_user_module_name'),
    )
    op.create_table('dashboard_preferences',
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('widgets_json',sa.Text(),nullable=False),
        sa.Column('layout_json',sa.Text(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_table('microsoft_integrations',
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('tenant_id',sa.String(120)),
        sa.Column('connected_email',sa.String(190)),
        sa.Column('scope',sa.Text()),
        sa.Column('encrypted_refresh_token',sa.Text()),
        sa.Column('connected_at',sa.DateTime()),
        sa.Column('updated_at',sa.DateTime(),server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_saved_views_user_module','saved_views',['user_id','module'])
    op.create_index('ix_fx_currency','fx_rates',['currency'])

def downgrade() -> None:
    op.drop_index('ix_fx_currency',table_name='fx_rates')
    op.drop_index('ix_saved_views_user_module',table_name='saved_views')
    op.drop_table('microsoft_integrations')
    op.drop_table('dashboard_preferences')
    op.drop_table('saved_views')
    op.drop_table('field_permissions')
    op.drop_table('fx_rates')
    op.drop_table('org_settings')
