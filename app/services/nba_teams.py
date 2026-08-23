"""Référence des 30 équipes NBA (nom complet <-> abréviation officielle).

Utilisé à deux endroits :
- l'import CSV équipes (Basketball-Reference ne fournit que le nom complet,
  pas l'abréviation) ;
- le parsing PDF des rapports de blessures (les noms d'équipe y sont collés
  sans espace, ex: "HoustonRockets" -> il faut les reconnaître pour les
  reformater et récupérer l'abréviation).
"""

NBA_TEAMS: dict[str, str] = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU",
    "Indiana Pacers": "IND",
    "LA Clippers": "LAC",
    "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}

# Alias reconnus en plus du nom officiel (variantes rencontrées dans les
# exports/rapports), mappés vers le nom complet officiel utilisé en base.
_ALIASES: dict[str, str] = {
    "Los Angeles Clippers": "LA Clippers",
}

# Index par version "collée sans espace, minuscule" du nom complet (+ alias)
# -> nom complet officiel. Sert à reconnaître les noms d'équipe extraits d'un
# PDF (où les espaces entre mots ont disparu) ou d'un CSV.
_COLLAPSED_TO_FULL_NAME: dict[str, str] = {
    **{full_name.replace(" ", "").lower(): full_name for full_name in NBA_TEAMS},
    **{alias.replace(" ", "").lower(): full_name for alias, full_name in _ALIASES.items()},
}

# Abréviation -> nom complet officiel (utile pour créer une Team à la volée
# quand un import joueurs arrive avant l'import équipes).
ABBREVIATION_TO_NAME: dict[str, str] = {abbr: full_name for full_name, abbr in NBA_TEAMS.items()}


def get_abbreviation(full_name: str) -> str | None:
    """Retourne l'abréviation officielle pour un nom complet d'équipe, ou None."""
    return NBA_TEAMS.get(full_name)


def get_full_name(abbreviation: str) -> str | None:
    """Retourne le nom complet officiel pour une abréviation, ou None."""
    return ABBREVIATION_TO_NAME.get(abbreviation)


def resolve_team_name(collapsed_or_full_name: str) -> str | None:
    """Reconnaît un nom d'équipe, avec ou sans espaces (ex: "HoustonRockets"
    ou "Houston Rockets"), et retourne le nom complet officiel, ou None si
    aucune équipe ne correspond.
    """
    if collapsed_or_full_name in NBA_TEAMS:
        return collapsed_or_full_name
    collapsed = collapsed_or_full_name.replace(" ", "").lower()
    return _COLLAPSED_TO_FULL_NAME.get(collapsed)
