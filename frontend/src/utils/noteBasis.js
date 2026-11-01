// Sur quelle MESURE repose la note de base de chaque équipe (voir pronostic_calculator.compute_note_de_base) :
//   - début de saison (moins de 10 matchs terminés) : les pourcentages de victoires de la saison PRÉCÉDENTE ;
//   - à partir de son 11e match : ceux de la saison EN COURS.
// Un match entre une équipe qui a basculé et une qui n'a pas basculé compare donc deux notes bâties sur des mesures
// différentes : l'écart n'a plus le même sens, et le favori peut changer pour une raison de calendrier, pas de terrain
// (étude de la falaise, 2026-11-01, Tools/etude_falaise/). La carte doit le dire.
//
// Lu dans breakdown.home/away.in_early_season, déjà stocké avec chaque pronostic : aucun champ nouveau. Un pronostic
// sans ce champ (ou non révélé) -> `known: false`, et la carte ne dit rien plutôt que de deviner.

export function noteBasis(breakdown, homeAbbreviation, awayAbbreviation) {
  // Ordre de la carte : l'extérieur d'abord, le domicile ensuite.
  const teams = [
    { abbreviation: awayAbbreviation, early: breakdown?.away?.in_early_season },
    { abbreviation: homeAbbreviation, early: breakdown?.home?.in_early_season },
  ]
  if (teams.some((t) => typeof t.early !== 'boolean')) {
    return { known: false, current: [], previous: [], mixed: false }
  }
  const current = teams.filter((t) => !t.early).map((t) => t.abbreviation)
  const previous = teams.filter((t) => t.early).map((t) => t.abbreviation)
  return { known: true, current, previous, mixed: current.length === 1 && previous.length === 1 }
}

// « ATL », « ATL et LAL » : jamais plus de deux équipes sur un match.
export function joinTeams(abbreviations) {
  return abbreviations.join(' et ')
}
