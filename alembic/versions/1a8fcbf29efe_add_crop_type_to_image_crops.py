"""add_crop_type_to_image_crops

Revision ID: 1a8fcbf29efe
Revises: f8542088a334
Create Date: 2026-04-28 23:49:27.807137

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a8fcbf29efe'
down_revision: Union[str, Sequence[str], None] = 'f8542088a334'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('image_crops', sa.Column('crop_type', sa.String(length=50), nullable=False, server_default='grid'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('image_crops', 'crop_type')
