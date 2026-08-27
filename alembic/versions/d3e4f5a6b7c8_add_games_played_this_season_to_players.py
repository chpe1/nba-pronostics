"""add games_played_this_season to players

Revision ID: d3e4f5a6b7c8
Revises: 3524f41debf4
Create Date: 2026-08-28 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, None] = '3524f41debf4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'players',
        sa.Column('games_played_this_season', sa.Integer(), server_default='0', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('players', 'games_played_this_season')
