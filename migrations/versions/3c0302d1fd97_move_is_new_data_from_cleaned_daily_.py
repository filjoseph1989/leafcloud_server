"""move_is_new_data_from_cleaned_daily_readings_to_daily_readings

Revision ID: 3c0302d1fd97
Revises: 276fc0e8b333
Create Date: 2026-05-18 22:46:10.309939

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c0302d1fd97'
down_revision: Union[str, Sequence[str], None] = '276fc0e8b333'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'daily_readings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('image_path', sa.String(255), nullable=True),
        sa.Column('ph', sa.Float(), nullable=True),
        sa.Column('ec', sa.Float(), nullable=True),
        sa.Column('water_temp', sa.Float(), nullable=True),
        sa.Column('status', sa.String(50), nullable=True),
        sa.Column('tank_id', sa.Integer(), nullable=True),
        sa.Column('experiment_id', sa.Integer(), nullable=True),
        sa.Column('is_new_data', sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.ForeignKeyConstraint(['experiment_id'], ['experiments.id'], name='daily_readings_experiment_id_fkey'),
        sa.ForeignKeyConstraint(['tank_id'], ['tank_configs.id'], name='daily_readings_tank_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='daily_readings_pkey'),
    )
    op.create_index('ix_daily_readings_id', 'daily_readings', ['id'], unique=False)
    op.drop_column('cleaned_daily_readings', 'is_new_data')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('cleaned_daily_readings', sa.Column('is_new_data', sa.BOOLEAN(), autoincrement=False, nullable=True))
    op.drop_index('ix_daily_readings_id', table_name='daily_readings')
    op.drop_table('daily_readings')
