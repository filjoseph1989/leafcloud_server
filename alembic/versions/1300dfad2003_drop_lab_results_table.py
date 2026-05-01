"""drop lab_results table

Revision ID: 1300dfad2003
Revises: f8542088a334
Create Date: 2026-05-01 01:12:01.761398

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1300dfad2003'
down_revision: Union[str, Sequence[str], None] = 'e79c2ce9b260'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index(op.f('ix_lab_results_sample_bottle_label'), table_name='lab_results')
    op.drop_index(op.f('ix_lab_results_id'), table_name='lab_results')
    op.drop_table('lab_results')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('lab_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sample_bottle_label', sa.String(length=50), nullable=True),
    sa.Column('n_val', sa.Float(), nullable=True),
    sa.Column('p_val', sa.Float(), nullable=True),
    sa.Column('k_val', sa.Float(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lab_results_id'), 'lab_results', ['id'], unique=False)
    op.create_index(op.f('ix_lab_results_sample_bottle_label'), 'lab_results', ['sample_bottle_label'], unique=True)
