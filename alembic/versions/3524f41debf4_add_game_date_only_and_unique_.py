"""add game_date_only and unique constraint on games

Revision ID: 3524f41debf4
Revises: 7396d3774d0b
Create Date: 2026-08-27 11:05:33.409581

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3524f41debf4'
down_revision: Union[str, None] = '7396d3774d0b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # game_date_only porte la vraie clé d'upsert du calendrier (date SANS
    # l'heure, home_team_id, away_team_id) -- game_date inclut l'heure, une
    # contrainte directe dessus ne collerait pas à la sémantique de
    # apply_schedule (csv_import.py). Backfill via date() de SQLite pour les
    # lignes existantes, puis colonne rendue NOT NULL et contrainte ajoutée
    # en une seule passe (Game._sync_game_date_only la tient à jour ensuite
    # automatiquement à chaque écriture de game_date).
    op.add_column("games", sa.Column("game_date_only", sa.Date(), nullable=True))
    op.execute("UPDATE games SET game_date_only = date(game_date)")
    with op.batch_alter_table("games") as batch_op:
        batch_op.alter_column("game_date_only", nullable=False)
        batch_op.create_unique_constraint(
            "uq_game_date_teams", ["game_date_only", "home_team_id", "away_team_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("games") as batch_op:
        batch_op.drop_constraint("uq_game_date_teams", type_="unique")
        batch_op.drop_column("game_date_only")
