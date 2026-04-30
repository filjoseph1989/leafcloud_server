"""add_additional_processed_to_progress

Revision ID: e79c2ce9b260
Revises: 1a8fcbf29efe
Create Date: 2026-04-29 00:59:30.439813

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e79c2ce9b260'
down_revision: Union[str, Sequence[str], None] = '1a8fcbf29efe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('image_crop_progress', sa.Column('additional_processed', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('image_crop_progress', 'additional_processed')
