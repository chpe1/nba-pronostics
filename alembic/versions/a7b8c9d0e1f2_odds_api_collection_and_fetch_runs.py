"""relevé automatique des cotes (the-odds-api.com) : origine du relevé, heure du bookmaker, journal des appels

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-11-03 22:00:00.000000

UNE seule migration pour tout le chantier (décision de l'utilisateur, 2026-11-03) :

  1. nouvelle table `odds_fetch_runs` : une ligne par appel à l'API, réussi ou non ;
  2. `odds.collection` (MANUEL / API), obligatoire : les lignes existantes, toutes saisies à la main, reçoivent
     MANUEL. Le défaut de colonne ne sert qu'à cette recopie et est retiré aussitôt : une écriture future qui
     oublierait de dire d'où vient sa cote doit échouer, pas devenir « manuelle » en silence ;
  3. `odds.bookmaker_updated_at` et `odds.fetch_run_id` (vides pour une saisie) ;
  4. `odds.market` élargi de VARCHAR(6) à VARCHAR(10) pour la valeur WINNER_LAY (vente sur une bourse d'échange) ;
  5. la contrainte d'unicité inclut `collection` ;
  6. SEULE écriture de données, accord explicite de l'utilisateur (2026-11-03, après comparaison des cotes de
     l'API aux sites de Winamax et d'Unibet) : source « winamax » -> « winamax_fr », « unibet » -> « unibet_fr ».
     Aucune autre valeur, aucune autre colonne n'est touchée.

SQLite : le mode batch recrée `odds` et recopie toutes les lignes (même procédé que f1a2b3c4d5e6). À contrôler
avant/après : nombre de lignes par source, total identique, toutes les autres colonnes identiques.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RENAMES = (("winamax", "winamax_fr"), ("unibet", "unibet_fr"))


def upgrade() -> None:
    op.create_table(
        "odds_fetch_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("trigger", sa.Enum("SCHEDULED", "BUTTON", name="oddsfetchtrigger"), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("credits_used", sa.Integer(), nullable=True),
        sa.Column("credits_remaining", sa.Integer(), nullable=True),
        sa.Column("events_returned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    with op.batch_alter_table("odds") as batch_op:
        batch_op.add_column(
            sa.Column("collection", sa.String(length=6), nullable=False, server_default="MANUEL")
        )
        batch_op.add_column(sa.Column("bookmaker_updated_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("fetch_run_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_odds_fetch_run", "odds_fetch_runs", ["fetch_run_id"], ["id"])
        batch_op.alter_column("market", existing_type=sa.String(length=6), type_=sa.String(length=10),
                              existing_nullable=False)
        batch_op.drop_constraint("uq_odds_snapshot", type_="unique")
        batch_op.create_unique_constraint(
            "uq_odds_snapshot", ["game_id", "market", "side", "source", "collection", "recorded_at"]
        )
    # Le défaut n'a servi qu'à remplir les lignes existantes : retiré (voir l'en-tête).
    with op.batch_alter_table("odds") as batch_op:
        batch_op.alter_column("collection", existing_type=sa.String(length=6), server_default=None,
                              existing_nullable=False)
    for old, new in RENAMES:
        op.execute(sa.text("UPDATE odds SET source = :new WHERE source = :old").bindparams(new=new, old=old))


def downgrade() -> None:
    # Refus EXPLICITE, avant toute modification, s'il existe une donnée que le schéma d'avant ne sait pas porter :
    # la supprimer en silence effacerait des relevés que le plan gratuit de l'API ne permet pas de récupérer.
    bind = op.get_bind()
    api_rows = bind.execute(sa.text("SELECT COUNT(*) FROM odds WHERE collection != 'MANUEL'")).scalar()
    lay_rows = bind.execute(sa.text("SELECT COUNT(*) FROM odds WHERE market = 'WINNER_LAY'")).scalar()
    runs = bind.execute(sa.text("SELECT COUNT(*) FROM odds_fetch_runs")).scalar()
    other_sources = bind.execute(
        sa.text("SELECT COUNT(*) FROM odds WHERE source NOT IN ('winamax_fr', 'unibet_fr')")
    ).scalar()
    if api_rows or lay_rows or runs or other_sources:
        raise RuntimeError(
            "Retour arrière refusé : la base contient des relevés automatiques ou des sources que le schéma "
            f"d'avant ne sait pas porter ({api_rows} cote(s) relevée(s) par l'API, {lay_rows} cote(s) de vente, "
            f"{runs} appel(s) journalisé(s), {other_sources} cote(s) d'une autre source que winamax_fr/unibet_fr). "
            "Les supprimer effacerait des relevés que le plan gratuit ne permet pas de récupérer."
        )
    for old, new in RENAMES:
        op.execute(sa.text("UPDATE odds SET source = :old WHERE source = :new").bindparams(new=new, old=old))
    with op.batch_alter_table("odds") as batch_op:
        batch_op.drop_constraint("uq_odds_snapshot", type_="unique")
        batch_op.create_unique_constraint(
            "uq_odds_snapshot", ["game_id", "market", "side", "source", "recorded_at"]
        )
        batch_op.alter_column("market", existing_type=sa.String(length=10), type_=sa.String(length=6),
                              existing_nullable=False)
        batch_op.drop_constraint("fk_odds_fetch_run", type_="foreignkey")
        batch_op.drop_column("fetch_run_id")
        batch_op.drop_column("bookmaker_updated_at")
        batch_op.drop_column("collection")
    op.drop_table("odds_fetch_runs")
