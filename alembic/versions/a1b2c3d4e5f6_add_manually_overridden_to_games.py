"""add manually_overridden to games

Revision ID: a1b2c3d4e5f6
Revises: 8f6de85f79e4
Create Date: 2026-08-24 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '8f6de85f79e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'games',
        sa.Column('manually_overridden', sa.Boolean(), server_default='0', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('games', 'manually_overridden')
