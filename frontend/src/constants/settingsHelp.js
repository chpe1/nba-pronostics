// Textes d'info-bulle des curseurs de l'algorithme, partagés entre
// AdminSettingsView.vue (Réglages généraux) et AdminTeamDiagnosticView.vue
// (panneau simulateur) -- une seule source pour ne jamais avoir deux
// explications différentes pour le même concept.
export const SETTINGS_HELP = {
  base_note_multiplier:
    "Transforme le pourcentage de victoires (0-1) en une note comparable aux autres composants de l'équation (PER, malus calendrier...) -- calibré pour une échelle 0-100 par défaut.",
  per_impact_multiplier:
    'Pondère le PER des joueurs absents (Out/Doubtful) avant de le soustraire à la note de base -- un PER brut (échelle ~10-30) écraserait sinon totalement une note calibrée sur 0-100.',
  transfer_impact_multiplier:
    "Pondère le PER (saison précédente) des joueurs arrivés ou partis cet été avant de l'ajouter ou de le retrancher à la note -- même principe que le Curseur B, actif uniquement pendant les 10 premiers matchs de la saison de l'équipe.",
  back_to_back_penalty:
    "Points retirés à la note d'une équipe qui joue un match au lendemain immédiat d'un précédent, sans jour de repos.",
  three_in_four_penalty:
    "Points retirés à une équipe qui dispute son 3e match en 4 nuits (fatigue cumulée). Si le back-to-back s'applique aussi au même match, seul le malus le plus sévère des deux est appliqué, jamais les deux cumulés.",
  mpg_threshold:
    "Temps de jeu minimum (minutes/match) pour qu'un joueur absent ou incertain soit pris en compte dans le calcul -- écarte les joueurs de fin de banc dont l'absence n'a pas d'impact réel.",
  player_sample_size_threshold:
    "Sous ce nombre de matchs joués cette saison par un joueur, son PER/MPG de la saison précédente est utilisé à la place de sa valeur courante (trop peu fiable sur un si petit échantillon). Distinct du seuil équipe de 10 matchs (début de saison) : un joueur précis peut y rester après un retour de blessure même si son équipe l'a dépassé.",
  reliability_threshold_low:
    'Écart de points minimum (après tous les bonus/malus) pour que la jauge de fiabilité du pronostic passe de Faible à Moyenne.',
  reliability_threshold_high:
    'Écart de points minimum pour que la jauge de fiabilité passe de Moyenne à Forte.',
  draft_bonus_config:
    'Bonus ajouté à la note d\'une équipe pour chaque rookie drafté dans son effectif (selon son pick, ex: {"1": 8, "2": 6}). Actif seulement pendant les 10 premiers matchs de la saison de l\'équipe.',
}
