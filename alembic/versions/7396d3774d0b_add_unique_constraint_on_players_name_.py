"""add unique constraint on players name team_id

Revision ID: 7396d3774d0b
Revises: b2c3d4e5f6a7
Create Date: 2026-08-27 11:05:13.079119

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7396d3774d0b'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Filet de sécurité complémentaire à find_player_by_name (comparaison
    # insensible à la casse côté code) -- bloque un doublon EXACT
    # (name, team_id) qui contournerait cette fonction suite à un bug futur
    # non anticipé. Ne détecte PAS "LeBron James" vs "LEBRON JAMES" : SQLite
    # ne replie que l'ASCII. Voir CLAUDE.md, "Décisions d'architecture".
    with op.batch_alter_table("players") as batch_op:
        batch_op.create_unique_constraint("uq_player_name_team", ["name", "team_id"])


def downgrade() -> None:
    with op.batch_alter_table("players") as batch_op:
        batch_op.drop_constraint("uq_player_name_team", type_="unique")
