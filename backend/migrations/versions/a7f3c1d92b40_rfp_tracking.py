"""RFP tracking tables

Revision ID: a7f3c1d92b40
Revises: 7c3e2f9a4d10
Create Date: 2026-09-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a7f3c1d92b40'
down_revision: Union[str, None] = '7c3e2f9a4d10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table('rfps',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('name',sa.String(220),nullable=False),
        sa.Column('description',sa.Text()),
        sa.Column('rfp_date',sa.String(10)),
        sa.Column('submission_eta',sa.String(10)),
        sa.Column('qa_timeline',sa.Text()),
        sa.Column('qa_status',sa.String(40),nullable=False,server_default='Not started'),
        sa.Column('technical_response',sa.Text()),
        sa.Column('pricing',sa.Text()),
        sa.Column('jsan_status',sa.String(40),nullable=False,server_default='Initiated'),
        sa.Column('vendor_status',sa.String(40),nullable=False,server_default='Initiated'),
        sa.Column('created_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(),server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at',sa.DateTime(),server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_table('rfp_documents',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('rfp_id',sa.Integer(),sa.ForeignKey('rfps.id',ondelete='CASCADE'),nullable=False),
        sa.Column('filename',sa.String(255),nullable=False),
        sa.Column('content_type',sa.String(120),nullable=False),
        sa.Column('size_bytes',sa.Integer(),nullable=False),
        sa.Column('sha256',sa.String(64),nullable=False),
        sa.Column('data',sa.LargeBinary(),nullable=False),
        sa.Column('uploaded_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(),server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_rfp_documents_rfp_id','rfp_documents',['rfp_id'])

def downgrade() -> None:
    op.drop_index('ix_rfp_documents_rfp_id',table_name='rfp_documents')
    op.drop_table('rfp_documents')
    op.drop_table('rfps')
