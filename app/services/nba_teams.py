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

# Basketball-Reference utilise pour certaines équipes une abréviation qui lui
# est propre, différente de l'abréviation officielle de la ligue utilisée
# comme référence dans NBA_TEAMS. "BRK" (Brooklyn) et "PHO" (Phoenix)
# rencontrés concrètement sur un vrai export (page Draft, colonne Tm) ;
# "CHO" (Charlotte) vérifié le 2026-08-25 par recherche systématique des 30
# abréviations réellement utilisées sur basketball-reference.com (pages
# d'équipe indexées) -- Basketball-Reference distingue ainsi les Hornets
# actuels (depuis 2014) de l'ancienne franchise Charlotte Hornets (1988-2002,
# devenue les Pelicans) qui utilisait déjà "CHH"/"CHA" dans son historique.
# Les 27 autres équipes (dont toutes celles ayant déménagé/changé de nom :
# NOP, OKC, MEM, UTA, LAC, GSW) confirmées identiques à l'abréviation
# canonique de NBA_TEAMS. Normalisées vers l'abréviation canonique AVANT
# toute validation/écriture en base, pour ne jamais créer une deuxième Team
# pour la même équipe. Liste tenue à jour au 2026-08-25 ; à revérifier si
# Basketball-Reference change ses conventions ou si une 30e franchise
# relocalise/se renomme.
_ABBREVIATION_ALIASES: dict[str, str] = {
    "BRK": "BKN",
    "PHO": "PHX",
    "CHO": "CHA",
}


def normalize_abbreviation(abbreviation: str) -> str:
    """Convertit une abréviation Basketball-Reference propriétaire (ex:
    "BRK", "PHO") vers l'abréviation canonique utilisée dans ABBREVIATION_TO_NAME
    (ex: "BKN", "PHX"). Retourne l'entrée telle quelle si elle n'est pas
    concernée (déjà canonique, ou véritablement inconnue -- la validation
    "équipe inconnue" reste à la charge de l'appelant)."""
    return _ABBREVIATION_ALIASES.get(abbreviation, abbreviation)


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
