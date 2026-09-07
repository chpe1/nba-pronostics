"""drop team conference, division and current_streak

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-09-07 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6b7c8d9e0f1'
down_revision: Union[str, None] = 'f5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('teams', 'conference')
    op.drop_column('teams', 'division')
    op.drop_column('teams', 'current_streak')


def downgrade() -> None:
    op.add_column('teams', sa.Column('conference', sa.String(length=20), nullable=True))
    op.add_column('teams', sa.Column('division', sa.String(length=30), nullable=True))
    op.add_column(
        'teams',
        sa.Column('current_streak', sa.Integer(), server_default='0', nullable=False),
    )
