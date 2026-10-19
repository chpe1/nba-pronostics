"""make players.team_id nullable (agents libres)

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-10-19 23:30:00.000000

Un joueur absent d'un fichier d'effectif importé devient « agent libre » : il
reste en base (historique, statistiques, retrouvé et replacé s'il réapparaît)
mais n'est plus rattaché à aucune équipe, donc `team_id` doit pouvoir être NULL.
Voir CLAUDE.md, Décision d'architecture n°39.

SQLite ne sait pas modifier la nullité d'une colonne : le mode batch recrée la
table `players` et recopie toutes les lignes. Contrainte UNIQUE(name, team_id),
clé étrangère vers `teams` : conservées par la recopie (vérifié, voir plan du
chantier). Attention : UNIQUE(name, team_id) ne protège PLUS les agents libres
entre eux -- SQLite traite chaque NULL comme distinct, deux agents libres
homonymes seraient donc admis ; la déduplication reste portée par le code.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'a6b7c8d9e0f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("players") as batch_op:
        batch_op.alter_column("team_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Refus EXPLICITE s'il existe un agent libre : remettre NOT NULL
    # échouerait de toute façon, mais avec une erreur d'intégrité obscure
    # ET après que la table a été recréée. On refuse avant de toucher à quoi
    # que ce soit, avec un message qui dit quoi faire.
    bind = op.get_bind()
    free_agents = bind.execute(sa.text("SELECT COUNT(*) FROM players WHERE team_id IS NULL")).scalar()
    if free_agents:
        raise RuntimeError(
            f"Retour arrière refusé : {free_agents} joueur(s) sont agent(s) libre(s) (players.team_id IS NULL). "
            "Remettre team_id en NOT NULL les ferait disparaître ou échouer. "
            "Rattachez-les d'abord à une équipe (écran Joueurs) ou supprimez-les, puis relancez le retour arrière."
        )
    with op.batch_alter_table("players") as batch_op:
        batch_op.alter_column("team_id", existing_type=sa.Integer(), nullable=False)
