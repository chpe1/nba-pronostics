"""Traitement complet d'un rapport de blessures déclenché à la main (bouton de
l'écran d'import) : téléchargement du rapport le plus récent, lecture,
rapprochement, application en base, compte-rendu structuré.

Ne modifie ni le rapprochement des noms (`injury_report_updater`) ni le calcul
des pronostics : il les appelle. Les écritures restent des `flush()` -- le
`commit()` est fait par la route, et seulement si quelque chose a été écrit.
"""
from __future__ import annotations

import collections
import io
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pdfplumber
from sqlalchemy.orm import Session

from app.models import Player, Settings, Team
from app.schemas.injury import (
    InjuryUnmatchedEntry,
    InjuryUpdateReport,
    InjuryWeighingPlayer,
)
from app.services.injury_report_fetcher import fetch_latest_report
from app.services.injury_report_parser import parse_injury_report_pdf
from app.services.injury_report_updater import (
    _normalize,
    apply_injury_report,
    build_match_key,
    resolve_player,
)

# Mêmes règles que le calcul des pronostics (statuts qui comptent comme absents,
# PER/MPG effectifs avec repli N-1) : on les réutilise, jamais recopiées ici.
from app.services.pronostic_calculator import ABSENT_STATUSES, _effective_per_mpg
from app.services.season import previous_season_label

PARIS_TIMEZONE = ZoneInfo("Europe/Paris")
_NOT_YET_SUBMITTED = "NOTYETSUBMITTED"
# Dates de match du rapport (année à 4 chiffres) ; le titre, lui, a une année à 2 chiffres.
_FULL_DATE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")


class InjuryReportReadError(Exception):
    pass


def _label(moment: datetime, zone_name: str) -> str:
    offset = moment.strftime("%z")
    return f"{moment:%d/%m/%Y %H:%M} ({zone_name}, UTC{offset[:3]}:{offset[3:]})"


def _read_pdf(content: bytes):
    """-> (entrées, nombre de « NOT YET SUBMITTED », dates de match lues dans le texte)."""
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            entries = parse_injury_report_pdf(pdf)
            text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception as exc:  # noqa: BLE001 -- on restitue le message réel de pdfplumber
        raise InjuryReportReadError(f"Lecture du PDF impossible : {exc!r}") from exc
    not_submitted = text.replace(" ", "").upper().count(_NOT_YET_SUBMITTED)
    dates: set[date] = set()
    for month, day, year in _FULL_DATE.findall(text):
        try:
            dates.add(date(int(year), int(month), int(day)))
        except ValueError:
            continue
    return entries, not_submitted, dates


def run_injury_update(db: Session, client=None, now: datetime | None = None) -> InjuryUpdateReport:
    fetched = fetch_latest_report(client=client, now=now)
    entries, not_submitted_count, text_dates = _read_pdf(fetched.content)

    settings = db.query(Settings).first()
    if settings is None:
        settings = Settings()
        db.add(settings)
        db.flush()
    threshold = settings.mpg_threshold
    prev_season = previous_season_label(settings.current_season)

    game_dates = sorted(text_dates | {e.game_date for e in entries if e.game_date})
    not_yet_submitted = not entries and not_submitted_count > 0

    base = dict(
        report_url=fetched.url,
        report_time_new_york=_label(fetched.report_time, "heure de New York"),
        report_time_paris=_label(fetched.report_time.astimezone(PARIS_TIMEZONE), "heure de Paris"),
        game_dates=[d.isoformat() for d in game_dates],
        entries_read=len(entries),
        not_yet_submitted=not_yet_submitted,
        not_yet_submitted_count=not_submitted_count,
        mpg_threshold=threshold,
    )

    if not entries:
        # Rien à écrire : rapport non soumis, ou rapport sans aucune entrée.
        return InjuryUpdateReport(
            **base,
            written=False,
            matched_count=0,
            unmatched_count=0,
            unmatched=[],
            status_counts={},
            absent_count=0,
            weighing_count=0,
            weighing=[],
        )

    team_abbreviation = {t.id: t.abbreviation for t in db.query(Team).all()}
    by_key: dict[str, list[Player]] = collections.defaultdict(list)
    for player in db.query(Player).all():
        by_key[_normalize(player.name)].append(player)

    matched: list[tuple[Player, object]] = []
    unmatched: list[InjuryUnmatchedEntry] = []
    for entry in entries:
        player = resolve_player(db, entry) if entry.status is not None else None
        if player is not None:
            matched.append((player, entry.status))
            continue
        others = by_key.get(build_match_key(entry.player_name_raw), [])
        unmatched.append(
            InjuryUnmatchedEntry(
                player_name_raw=entry.player_name_raw,
                team_abbreviation=entry.team_abbreviation,
                team_raw=entry.team_raw,
                status_raw=entry.status_raw,
                reason=entry.reason,
                # Un agent libre (team_id NULL, Décision n°39) n'a pas d'abréviation : il n'entre pas dans cette
                # liste (jamais de KeyError) et fait l'objet de son propre drapeau.
                exists_in_database_on_teams=sorted(
                    {
                        team_abbreviation[p.team_id]
                        for p in others
                        if p.team_id is not None and team_abbreviation[p.team_id] != entry.team_abbreviation
                    }
                ),
                exists_in_database_as_free_agent=any(p.team_id is None for p in others),
            )
        )

    apply_injury_report(db, entries)

    status_counts = collections.Counter(status.value for _, status in matched)
    absent = {p.id: (p, s) for p, s in matched if s in ABSENT_STATUSES}
    weighing: list[InjuryWeighingPlayer] = []
    for player, status in absent.values():
        per, mpg = _effective_per_mpg(db, player, prev_season, settings)
        if mpg > threshold:
            weighing.append(
                InjuryWeighingPlayer(
                    name=player.name,
                    team_abbreviation=team_abbreviation[player.team_id],
                    status=status.value,
                    per=per,
                    mpg=mpg,
                )
            )
    weighing.sort(key=lambda w: (w.team_abbreviation, w.name))

    return InjuryUpdateReport(
        **base,
        written=True,
        matched_count=len(matched),
        unmatched_count=len(unmatched),
        unmatched=unmatched,
        status_counts=dict(status_counts),
        absent_count=len(absent),
        weighing_count=len(weighing),
        weighing=weighing,
    )
