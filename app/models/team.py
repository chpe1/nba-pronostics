from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.player import Player
    from app.models.game import Game


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    abbreviation: Mapped[str] = mapped_column(String(5), unique=True, nullable=False)
    conference: Mapped[str | None] = mapped_column(String(20), nullable=True)
    division: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Note de base (% de victoires), saison en cours
    win_pct_home: Mapped[float] = mapped_column(Float, default=0.0)
    win_pct_away: Mapped[float] = mapped_column(Float, default=0.0)

    # Saison N-1, utilisé pour la règle des 10 premiers matchs
    win_pct_home_prev_season: Mapped[float] = mapped_column(Float, default=0.0)
    win_pct_away_prev_season: Mapped[float] = mapped_column(Float, default=0.0)

    # Série en cours : positif = victoires, négatif = défaites (ex: +3, -2)
    current_streak: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    players: Mapped[list["Player"]] = relationship(
        "Player",
        back_populates="team",
        foreign_keys="Player.team_id",
    )
    home_games: Mapped[list["Game"]] = relationship(
        "Game",
        back_populates="home_team",
        foreign_keys="Game.home_team_id",
    )
    away_games: Mapped[list["Game"]] = relationship(
        "Game",
        back_populates="away_team",
        foreign_keys="Game.away_team_id",
    )

    def __repr__(self) -> str:
        return f"<Team {self.abbreviation}>"
