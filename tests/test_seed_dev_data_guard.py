"""Garde-fou de scripts/seed_dev_data.py : c'est le seul endroit du projet où un
bug peut détruire de vraies données (Team/Player/Game/Prediction remplacés sans
confirmation) -- il mérite une couverture dédiée, symétrique (refus ET passage),
pas seulement le cas qui ne casse rien."""
import pytest

from scripts.seed_dev_data import REAL_DATABASE_URL, ensure_not_real_database, resolve_sqlite_path


def test_resolve_sqlite_path_returns_none_for_in_memory_db():
    assert resolve_sqlite_path("sqlite:///:memory:") is None


def test_ensure_not_real_database_allows_a_genuinely_separate_file(tmp_path):
    dev_url = f"sqlite:///{(tmp_path / 'nba_pronostics_dev.db').as_posix()}"
    ensure_not_real_database(dev_url)  # ne doit lever aucune exception


def test_ensure_not_real_database_refuses_the_real_url_as_is():
    with pytest.raises(SystemExit):
        ensure_not_real_database(REAL_DATABASE_URL)


def test_ensure_not_real_database_refuses_an_absolute_path_to_the_same_file():
    # Le coeur de l'exigence : une URL de forme différente (chemin absolu au
    # lieu du chemin relatif par défaut) mais qui désigne le MÊME fichier une
    # fois résolue doit être refusée aussi -- comparaison sur le chemin
    # résolu, jamais sur la chaîne brute de l'URL.
    absolute_equivalent = resolve_sqlite_path(REAL_DATABASE_URL)
    url = f"sqlite:///{absolute_equivalent.as_posix()}"

    assert url != REAL_DATABASE_URL  # les deux chaînes doivent être différentes...
    with pytest.raises(SystemExit):
        ensure_not_real_database(url)  # ...pour que ce refus prouve la comparaison par chemin
