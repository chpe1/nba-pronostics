from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.services.season import previous_season_label


class Settings(Base):
    """Réglages de l'algorithme (curseurs du back-office).

    Table à ligne unique : une seule ligne de configuration active
    (convention appliquée au niveau du service, pas d'une contrainte SQL).
    """

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Curseur A : multiplicateur de la note de base (% de victoires).
    # Ramène win_pct (0-1) sur une échelle de "points" 0-100, pour être
    # comparable au PER une fois pondéré par le Curseur B. Voir
    # docs/calibrage-v1.md pour le raisonnement complet.
    base_note_multiplier: Mapped[float] = mapped_column(Float, default=100.0)
    # Curseur B : multiplicateur d'impact du PER des absents.
    per_impact_multiplier: Mapped[float] = mapped_column(Float, default=0.4)

    back_to_back_penalty: Mapped[float] = mapped_column(Float, default=2.0)
    three_in_four_penalty: Mapped[float] = mapped_column(Float, default=3.5)

    # Seuil de temps de jeu (MPG) minimum pour la prise en compte du PER
    mpg_threshold: Mapped[float] = mapped_column(Float, default=15.0)

    # Garde-fou petit échantillon INDIVIDUEL (par joueur, sur son nombre de
    # matchs joués cette saison) : distinct de EARLY_SEASON_GAME_THRESHOLD
    # (équipe, pronostic_calculator.py) -- un joueur précis peut rester sous
    # ce seuil alors que son équipe a dépassé le sien (retour de blessure,
    # call-up en cours de saison). Sous ce seuil, PER/MPG N-1 utilisés à la
    # place des valeurs courantes si disponibles (voir compute_injury_penalty).
    # Non calibré par simulation (pas de vraies données) -- voir docs/calibrage-v1.md.
    player_sample_size_threshold: Mapped[int] = mapped_column(Integer, default=5)

    # Bonus Draft par pick, ex: {"1": 8.0, "2": 6.0, ...} (échelle 0-100 points)
    draft_bonus_config: Mapped[dict] = mapped_column(JSON, default=dict)

    # Curseur Bonus/Malus Transferts : pondère le PER (N-1) des joueurs
    # transférés (Étape 6bis). Aligné par défaut sur per_impact_multiplier ;
    # non validé par simulation (voir docs/calibrage-v1.md).
    transfer_impact_multiplier: Mapped[float] = mapped_column(Float, default=0.4)

    # Seuils de l'Indice de Fiabilité, sur l'écart absolu entre les deux
    # notes finales : < low -> Faible, [low, high) -> Moyenne, >= high -> Forte.
    # Calibrés (V1) sur la distribution réelle des |spread| obtenue sur un
    # calendrier simulé -- voir docs/calibrage-v1.md.
    reliability_threshold_low: Mapped[float] = mapped_column(Float, default=7.0)
    reliability_threshold_high: Mapped[float] = mapped_column(Float, default=30.0)

    # Saison courante ("2026-2027"), modifiable par l'admin une fois par an
    # (back-office Réglages) -- jamais déduite automatiquement d'une date
    # (décision déjà prise à l'Étape 6ter pour les mêmes raisons). Sert à
    # pré-remplir le champ saison du formulaire d'import CSV.
    current_season: Mapped[str] = mapped_column(String(9), default="2026-2027")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    @property
    def previous_season(self) -> str:
        """Dérivée de current_season, jamais stockée séparément -- évite
        que les deux valeurs se désynchronisent."""
        return previous_season_label(self.current_season)

    def __repr__(self) -> str:
        return f"<Settings id={self.id}>"
