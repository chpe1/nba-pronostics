"""add point diff prev season and win probability columns

Probabilité de victoire construite À CÔTÉ de la note (modèle d'écart de points, étude Tools/etude_amorcage) :
uniquement des AJOUTS de colonnes, toutes vides par défaut (NULL). Aucune colonne existante n'est modifiée,
aucune donnée n'est écrite. NULL n'est jamais 0 : un écart N-1 vide rend la probabilité incalculable, il ne
la fausse pas.

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-10-26 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0f1a2b3c4d5'
down_revision: Union[str, None] = 'd9e0f1a2b3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PREDICTION_COLUMNS = (
    'probability_model_version',
    'expected_margin',
    'home_win_probability',
    'probability_inputs',
)


def upgrade() -> None:
    with op.batch_alter_table('teams') as batch_op:
        batch_op.add_column(sa.Column('point_diff_prev_season', sa.Float(), nullable=True))
    with op.batch_alter_table('predictions') as batch_op:
        batch_op.add_column(sa.Column('probability_model_version', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('expected_margin', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('home_win_probability', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('probability_inputs', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Retour arrière : retire les colonnes ajoutées, et elles seules. Les valeurs saisies dedans (écarts N-1,
    # probabilités) sont perdues -- c'est le prix d'un retour arrière, à savoir avant de le lancer.
    with op.batch_alter_table('predictions') as batch_op:
        for name in reversed(PREDICTION_COLUMNS):
            batch_op.drop_column(name)
    with op.batch_alter_table('teams') as batch_op:
        batch_op.drop_column('point_diff_prev_season')
