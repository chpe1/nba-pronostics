"""add odds table

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-10-24 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9e0f1a2b3c4'
down_revision: Union[str, None] = 'c8d9e0f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'odds',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('game_id', sa.Integer(), sa.ForeignKey('games.id'), nullable=False),
        sa.Column('market', sa.Enum('winner', name='oddsmarket'), nullable=False, server_default='winner'),
        sa.Column('side', sa.Enum('home', 'away', name='oddsside'), nullable=False),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('game_id', 'market', 'side', 'source', 'recorded_at', name='uq_odds_snapshot'),
    )


def downgrade() -> None:
    op.drop_table('odds')
