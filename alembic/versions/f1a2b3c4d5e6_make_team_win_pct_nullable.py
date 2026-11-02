"""make teams.win_pct_home / win_pct_away nullable (pourcentages calculés, chantier (b2))

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-11-02 20:00:00.000000

Les pourcentages de victoires de la saison en cours sont désormais calculés par le moteur depuis les matchs terminés
(app/services/team_win_pct.py). Un côté sans aucun match compté doit valoir NULL (inconnu), JAMAIS 0 : un zéro
stocké qui veut dire « je ne sais pas » est exactement la panne silencieuse de la limitation n°30. Voir CLAUDE.md.

Schéma seulement : AUCUNE donnée n'est modifiée (les 0,0 actuels restent 0,0 jusqu'au premier recalcul, déclenché
par la prochaine synchronisation des scores).

SQLite ne sait pas modifier la nullité d'une colonne : le mode batch recrée la table `teams` et recopie toutes les
lignes (même procédé que b7c8d9e0f1a2 pour `players`). Les clés étrangères de `players`, `games`, etc. désignent la
table par son NOM et restent valides après la recopie ; contraintes UNIQUE(name) et UNIQUE(abbreviation) conservées.
À vérifier après coup : PRAGMA integrity_check, PRAGMA foreign_key_check, nombre de lignes de chaque table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e0f1a2b3c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("teams") as batch_op:
        batch_op.alter_column("win_pct_home", existing_type=sa.Float(), nullable=True)
        batch_op.alter_column("win_pct_away", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    # Refus EXPLICITE, avant toute modification, s'il existe une valeur NULL : la remettre en NOT NULL demanderait
    # de la remplacer par 0, c'est-à-dire de recréer le zéro silencieux que cette migration supprime.
    bind = op.get_bind()
    nulls = bind.execute(
        sa.text("SELECT COUNT(*) FROM teams WHERE win_pct_home IS NULL OR win_pct_away IS NULL")
    ).scalar()
    if nulls:
        raise RuntimeError(
            f"Retour arrière refusé : {nulls} équipe(s) ont un pourcentage de victoires inconnu (NULL). "
            "Le remettre en NOT NULL obligerait à écrire 0 à la place de « inconnu » (limitation n°30). "
            "Renseignez ces valeurs (import du classement de la saison en cours) puis relancez le retour arrière."
        )
    with op.batch_alter_table("teams") as batch_op:
        batch_op.alter_column("win_pct_home", existing_type=sa.Float(), nullable=False)
        batch_op.alter_column("win_pct_away", existing_type=sa.Float(), nullable=False)
