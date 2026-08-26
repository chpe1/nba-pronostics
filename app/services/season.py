"""Aide-mémoire autour de la saison courante (Settings.current_season).

La saison courante est un réglage admin modifiable manuellement (une fois
par an), jamais déduite automatiquement d'une date -- décision déjà prise à
l'Étape 6ter pour les mêmes raisons (aucun moyen fiable de déterminer, à
partir de la seule date du jour, si l'intersaison est terminée ou non).
"""
from __future__ import annotations


def previous_season_label(season: str) -> str:
    """"2026-2027" -> "2025-2026"."""
    start_year, end_year = season.split("-")
    return f"{int(start_year) - 1}-{int(end_year) - 1}"
