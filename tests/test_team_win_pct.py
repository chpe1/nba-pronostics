"""Pourcentages de victoires de la saison en cours calculés depuis les matchs terminés (chantier (b2), limitation n°30).

Couvre : la preuve de la formule sur une saison réelle complète (2025-2026, 30 équipes, égalité EXACTE avec le classement
officiel importé), la règle « côté vide = None, jamais 0 », les matchs exclus, la note qui reste sur la saison précédente
faute d'un côté, les quatre chemins d'écriture de score, et l'affichage recompté de l'écran Équipes.
"""
import csv
from datetime import date, datetime
from pathlib import Path

import pytest

from app.models import Game, GameStatus, Settings, Team
from app.services import csv_import
from app.services.nba_teams import NBA_TEAMS
from app.services.pronostic_calculator import EARLY_SEASON_GAME_THRESHOLD, compute_team_note
from app.services.team_win_pct import (
    EXCLUDED_NO_SCORE,
    EXCLUDED_TIE,
    count_season_records,
    recompute_current_season_win_pct,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SEASON = "2026-2027"


def _settings(db_session, season=SEASON) -> Settings:
    settings = Settings(current_season=season)
    db_session.add(settings)
    db_session.flush()
    return settings


def _team(db_session, abbreviation, name=None, **kwargs) -> Team:
    team = Team(name=name or f"Équipe {abbreviation}", abbreviation=abbreviation, **kwargs)
    db_session.add(team)
    db_session.flush()
    return team


def _game(db_session, home, away, day, scores=(None, None), status=GameStatus.FINISHED, season=SEASON) -> Game:
    game = Game(season=season, game_date=datetime.combine(day, datetime.min.time()).replace(hour=19),
                home_team_id=home.id, away_team_id=away.id, status=status,
                home_score=scores[0], away_score=scores[1])
    db_session.add(game)
    db_session.flush()
    return game


# --- 7. Preuve de la formule sur une saison réelle --------------------------------------------------------------------

def test_formula_reproduces_exactly_the_official_2025_26_home_road_percentages_for_all_30_teams(db_session):
    """Les 1230 matchs de saison régulière 2025-2026 (balldontlie ; finale de NBA Cup et play-in exclus, comme au
    classement officiel) redonnent, à l'égalité STRICTE des flottants, les pourcentages domicile/extérieur du vrai
    classement « Expanded Standings » importé en N-1 -- lu par le parseur de l'import, pas recopié à la main."""
    _settings(db_session, season="2025-2026")
    teams = {abbr: _team(db_session, abbr, name) for name, abbr in NBA_TEAMS.items()}

    with open(FIXTURES_DIR / "matchs_saison_25_26.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1230
    for r in rows:
        _game(db_session, teams[r["home"]], teams[r["away"]], date.fromisoformat(r["date"]),
              scores=(int(r["home_score"]), int(r["away_score"])), season="2025-2026")

    assert recompute_current_season_win_pct(db_session) == 30

    official, errors = csv_import.parse_teams_home_away(
        csv_import.read_csv((FIXTURES_DIR / "classement_saison_25_26.csv").read_bytes())
    )
    assert errors == [] and len(official) == 30
    for item in official:
        team = teams[item["abbreviation"]]
        assert (team.win_pct_home, team.win_pct_away) == (item["win_pct_home"], item["win_pct_away"]), item["name"]
    records = count_season_records(db_session, "2025-2026")
    assert all(r.home.games + r.away.games == 82 for r in records.by_team.values())


# --- 3. Côté vide : None, jamais 0 -----------------------------------------------------------------------------------

def test_side_without_any_counted_game_is_none_never_zero(db_session):
    """Contre-épreuve de la limitation n°30 : une équipe qui n'a joué qu'à l'extérieur a un pourcentage domicile
    INCONNU. Écrire 0 ici (ou garder un 0 hérité) ferait échouer ce test."""
    _settings(db_session)
    a = _team(db_session, "AAA", win_pct_home=0.0, win_pct_away=0.0)  # ancien état : 0 partout
    b = _team(db_session, "BBB")
    _game(db_session, b, a, date(2026, 10, 21), scores=(100, 110))  # A gagne à l'extérieur
    _game(db_session, b, a, date(2026, 10, 23), scores=(120, 90))  # A perd à l'extérieur

    recompute_current_season_win_pct(db_session)

    assert a.win_pct_home is None
    assert a.win_pct_away == 0.5
    assert b.win_pct_home == 0.5
    assert b.win_pct_away is None


def test_a_real_zero_stays_zero_when_games_were_counted(db_session):
    """0 n'est pas interdit : il veut dire « tous perdus », à condition qu'il y ait eu des matchs."""
    _settings(db_session)
    a, b = _team(db_session, "AAA"), _team(db_session, "BBB")
    _game(db_session, a, b, date(2026, 10, 21), scores=(90, 100))
    recompute_current_season_win_pct(db_session)
    assert a.win_pct_home == 0.0
    assert b.win_pct_away == 1.0


# --- Matchs comptés / exclus -----------------------------------------------------------------------------------------

def test_only_finished_games_with_two_different_scores_of_the_current_season_are_counted(db_session):
    _settings(db_session)
    a, b = _team(db_session, "AAA"), _team(db_session, "BBB")
    _game(db_session, a, b, date(2026, 10, 21), scores=(110, 100))  # compté
    no_score = _game(db_session, a, b, date(2026, 10, 22), scores=(None, None))  # terminé sans score
    half_score = _game(db_session, a, b, date(2026, 10, 23), scores=(101, None))  # un seul score
    tie = _game(db_session, a, b, date(2026, 10, 24), scores=(99, 99))  # égalité
    _game(db_session, a, b, date(2026, 10, 25), status=GameStatus.SCHEDULED)
    _game(db_session, a, b, date(2026, 10, 26), status=GameStatus.POSTPONED)
    _game(db_session, a, b, date(2026, 4, 1), scores=(80, 120), season="2025-2026")  # autre saison

    records = count_season_records(db_session, SEASON)
    assert (records.for_team(a.id).home.wins, records.for_team(a.id).home.losses) == (1, 0)
    assert records.for_team(a.id).last_game_date == date(2026, 10, 21)
    assert [(g.game_id, g.reason) for g in records.excluded] == [
        (no_score.id, EXCLUDED_NO_SCORE), (half_score.id, EXCLUDED_NO_SCORE), (tie.id, EXCLUDED_TIE),
    ]


def test_neutral_site_game_keeps_the_home_team_designated_by_the_database(db_session):
    """Terrain neutre (ex. NBA Cup à Las Vegas) : aucune donnée ne le distingue, le match compte pour le côté que la base
    désigne -- domicile pour `home_team_id`."""
    _settings(db_session)
    a, b = _team(db_session, "AAA"), _team(db_session, "BBB")
    _game(db_session, a, b, date(2026, 12, 16), scores=(110, 100))
    recompute_current_season_win_pct(db_session)
    assert (a.win_pct_home, a.win_pct_away) == (1.0, None)


def test_recompute_without_settings_row_writes_nothing(db_session):
    a, b = _team(db_session, "AAA", win_pct_home=0.3, win_pct_away=0.4), _team(db_session, "BBB")
    _game(db_session, a, b, date(2026, 10, 21), scores=(110, 100))
    assert recompute_current_season_win_pct(db_session) == 0
    assert (a.win_pct_home, a.win_pct_away) == (0.3, 0.4)


# --- La note : bascule seulement si les deux côtés sont définis --------------------------------------------------------

def _ten_finished_games(db_session, team, opponent, home_count):
    for i in range(EARLY_SEASON_GAME_THRESHOLD):
        day = date(2026, 10, 21 + i)
        if i < home_count:
            _game(db_session, team, opponent, day, scores=(110, 100))
        else:
            _game(db_session, opponent, team, day, scores=(100, 110))


def test_team_with_ten_games_but_an_empty_side_stays_on_previous_season(db_session):
    """Exigence de l'utilisateur : la base RÉELLEMENT utilisée se lit dans `in_early_season` (la carte le lit). Une
    équipe à 10 matchs sans aucun match à domicile reste sur la saison précédente, et la carte dira « saison
    précédente »."""
    settings = _settings(db_session)
    team = _team(db_session, "AAA", win_pct_home_prev_season=0.6, win_pct_away_prev_season=0.45)
    opponent = _team(db_session, "BBB")
    _ten_finished_games(db_session, team, opponent, home_count=0)
    recompute_current_season_win_pct(db_session)
    assert team.win_pct_home is None and team.win_pct_away == 1.0

    breakdown = compute_team_note(db_session, team, date(2026, 11, 5), SEASON, is_home=False, settings=settings)

    assert breakdown.games_played_this_season == EARLY_SEASON_GAME_THRESHOLD
    assert breakdown.in_early_season is True
    assert breakdown.current_pct_missing is True
    assert breakdown.note_de_base == 0.45  # N-1 extérieur, PAS le 1.0 de la saison en cours


def test_team_with_ten_games_and_both_sides_defined_switches_to_current_season(db_session):
    settings = _settings(db_session)
    team = _team(db_session, "AAA", win_pct_home_prev_season=0.6, win_pct_away_prev_season=0.45)
    opponent = _team(db_session, "BBB")
    _ten_finished_games(db_session, team, opponent, home_count=4)
    recompute_current_season_win_pct(db_session)

    breakdown = compute_team_note(db_session, team, date(2026, 11, 5), SEASON, is_home=False, settings=settings)

    assert breakdown.in_early_season is False
    assert breakdown.current_pct_missing is False
    assert breakdown.note_de_base == 1.0


def test_empty_side_before_the_tenth_game_is_not_flagged_as_missing(db_session):
    """Avant 10 matchs, l'équipe est en début de saison de toute façon : `current_pct_missing` reste faux (il n'explique
    que le cas au-delà du seuil)."""
    settings = _settings(db_session)
    team, opponent = _team(db_session, "AAA"), _team(db_session, "BBB")
    _game(db_session, opponent, team, date(2026, 10, 21), scores=(100, 110))
    recompute_current_season_win_pct(db_session)
    breakdown = compute_team_note(db_session, team, date(2026, 11, 5), SEASON, is_home=True, settings=settings)
    assert breakdown.in_early_season is True and breakdown.current_pct_missing is False


# --- 2. Chemins d'écriture de score -----------------------------------------------------------------------------------

def test_manual_score_correction_on_games_screen_recomputes(client, db_session, auth_headers):
    _settings(db_session)
    a, b = _team(db_session, "AAA"), _team(db_session, "BBB")
    game = _game(db_session, a, b, date(2026, 10, 21), status=GameStatus.SCHEDULED)
    db_session.commit()

    response = client.patch(f"/api/games/{game.id}", json={"home_score": 120, "away_score": 100}, headers=auth_headers)
    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(Team, a.id).win_pct_home == 1.0
    assert db_session.get(Team, b.id).win_pct_away == 0.0

    client.patch(f"/api/games/{game.id}", json={"home_score": 90}, headers=auth_headers)  # correction : défaite
    db_session.expire_all()
    assert db_session.get(Team, a.id).win_pct_home == 0.0


def test_deleting_a_finished_game_recomputes(client, db_session, auth_headers):
    _settings(db_session)
    a, b = _team(db_session, "AAA"), _team(db_session, "BBB")
    game = _game(db_session, a, b, date(2026, 10, 21), scores=(110, 100))
    recompute_current_season_win_pct(db_session)
    db_session.commit()
    assert a.win_pct_home == 1.0

    assert client.delete(f"/api/games/{game.id}", headers=auth_headers).status_code == 204
    db_session.expire_all()
    assert db_session.get(Team, a.id).win_pct_home is None


def test_schedule_import_carrying_scores_recomputes(db_session):
    _settings(db_session)
    a = _team(db_session, "BOS", name="Boston Celtics")
    b = _team(db_session, "DET", name="Detroit Pistons")
    parsed = [{"game_date": date(2026, 10, 21), "game_time": datetime.min.time().replace(hour=19),
               "home_team_abbreviation": "BOS", "away_team_abbreviation": "DET", "home_score": 100, "away_score": 95}]
    csv_import.apply_schedule(parsed, db_session, SEASON)
    assert (a.win_pct_home, b.win_pct_away) == (1.0, 0.0)


def test_current_season_standings_import_writes_none_for_a_side_without_games(db_session):
    """Filet de sécurité (import manuel, toujours actif) : un côté « 0-0 » dans le fichier devient inconnu, pas 0. Le
    chemin N-1 garde son comportement."""
    parsed = [{"name": "Boston Celtics", "abbreviation": "BOS", "win_pct_home": 0.0, "win_pct_away": 0.75,
               "home_games": 0, "road_games": 4}]
    csv_import.apply_teams_home_away(parsed, db_session)
    team = db_session.query(Team).filter(Team.abbreviation == "BOS").one()
    assert (team.win_pct_home, team.win_pct_away) == (None, 0.75)

    csv_import.apply_teams_home_away_prev_season(parsed, db_session)
    assert team.win_pct_home_prev_season == 0.0  # N-1 inchangé (saison complète : jamais vide en pratique)


# --- 4. Écran Équipes : recompté à l'affichage -----------------------------------------------------------------------

def test_teams_route_shows_counts_last_game_and_flags_a_stored_value_that_differs(client, db_session):
    _settings(db_session)
    a, b = _team(db_session, "AAA"), _team(db_session, "BBB")
    _game(db_session, a, b, date(2026, 10, 21), scores=(110, 100))
    _game(db_session, b, a, date(2026, 10, 23), scores=(110, 100))
    no_score = _game(db_session, a, b, date(2026, 10, 25))
    recompute_current_season_win_pct(db_session)
    b.win_pct_home = 0.0  # valeur stockée périmée (ex. import manuel) : doit se voir
    db_session.commit()

    body = {t["abbreviation"]: t for t in client.get("/api/teams").json()}

    rec_a = body["AAA"]["current_season_record"]
    assert rec_a["season"] == SEASON
    assert rec_a["home"] == {"wins": 1, "losses": 0, "games": 1, "pct": 1.0}
    assert rec_a["away"] == {"wins": 0, "losses": 1, "games": 1, "pct": 0.0}
    assert rec_a["last_game_date"] == "2026-10-23"
    assert rec_a["stored_matches_recount"] is True
    assert rec_a["excluded_games"] == [{"game_id": no_score.id, "game_date": "2026-10-25", "reason": EXCLUDED_NO_SCORE}]

    rec_b = body["BBB"]["current_season_record"]
    assert rec_b["home"]["pct"] == 1.0 and body["BBB"]["win_pct_home"] == 0.0
    assert rec_b["stored_matches_recount"] is False


def test_teams_route_without_settings_has_no_record(client, db_session):
    _team(db_session, "AAA")
    db_session.commit()
    assert client.get("/api/teams").json()[0]["current_season_record"] is None


# --- Synchronisation balldontlie : bouton et tâche planifiée ----------------------------------------------------------

def _balldontlie_client(day, home_score, away_score):
    import httpx

    payload = {"data": [{"date": day.isoformat(), "status_state": "final", "postponed": False,
                         "home_team": {"abbreviation": "AAA"}, "visitor_team": {"abbreviation": "BBB"},
                         "home_team_score": home_score, "visitor_team_score": away_score}], "meta": {}}
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))


def test_scheduled_sync_recomputes_in_the_same_transaction(db_session):
    from app.services.scores_fetcher import sync_scores_for_date

    _settings(db_session)
    a, b = _team(db_session, "AAA"), _team(db_session, "BBB")
    day = date(2026, 10, 21)
    _game(db_session, a, b, day, status=GameStatus.SCHEDULED)

    result = sync_scores_for_date(db_session, "cle", day, client=_balldontlie_client(day, 120, 100))

    assert result.updated == 1 and result.win_pct_teams_updated == 2
    db_session.expire_all()
    assert db_session.get(Team, a.id).win_pct_home == 1.0  # validé (commit), pas seulement en mémoire


def test_sync_button_recomputes_even_without_a_new_score_and_reports_it(client, db_session, auth_headers, monkeypatch):
    """Le bouton recalcule à chaque passage : une valeur stockée périmée (ici 0, l'état d'avant (b2)) est corrigée même
    si aucun score n'a changé, et le compte-rendu le dit (écriture en base : oui)."""
    from app.api import scores as scores_api
    from app.services.scores_fetcher import sync_scores_for_range as real_sync

    monkeypatch.setenv("BALLDONTLIE_API_KEY", "cle")
    _settings(db_session)
    a = _team(db_session, "AAA", win_pct_home=0.0, win_pct_away=0.0)
    b = _team(db_session, "BBB", win_pct_home=0.0, win_pct_away=0.0)
    day = date(2026, 10, 21)
    _game(db_session, a, b, day, scores=(120, 100))  # déjà terminé, déjà à jour
    db_session.commit()
    fake = _balldontlie_client(day, 120, 100)
    monkeypatch.setattr(scores_api, "sync_scores_for_range",
                        lambda db, key, start, end: real_sync(db, key, start, end, client=fake))

    body = client.post("/api/scores/sync", params={"date_from": day.isoformat(), "date_to": day.isoformat()},
                       headers=auth_headers).json()

    assert body["recorded_count"] == 0 and body["already_final_count"] == 1
    assert body["win_pct_teams_updated"] == 2 and body["written"] is True
    db_session.expire_all()
    assert (db_session.get(Team, a.id).win_pct_home, db_session.get(Team, a.id).win_pct_away) == (1.0, None)
