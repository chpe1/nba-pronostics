// Logique de comptage des pastilles de contexte (docs/design-v1.md §10.4),
// partagée entre GameCard.vue (rendu par carte) et DashboardView.vue (calcul
// de la hauteur réservée sur l'ensemble des cartes de la vue courante -- voir
// §10.3, correction du 2026-08-30 : la réserve se cale sur le maximum réel de
// la vue, pas sur le plafond théorique de 3).

// Statut calendaire : purement calendaire, jamais masqué même pour un match
// non révélé -- le calendrier de la saison est connu à l'avance.
export function calendarLabels(status) {
  if (!status) return []
  const labels = []
  if (status.is_back_to_back) labels.push('B2B')
  if (status.is_three_in_four) labels.push('3-en-4')
  return labels
}

function breakdownSide(game, side) {
  const prediction = game.prediction
  const isRevealed = Boolean(prediction) && !prediction.is_upcoming
  if (!isRevealed) return { absentPlayers: [], questionablePlayers: [] }
  return {
    absentPlayers: prediction.breakdown?.[side]?.absent_players ?? [],
    questionablePlayers: prediction.breakdown?.[side]?.questionable_players ?? [],
  }
}

// Nombre de faits bruts pour une équipe (absents + incertains + calendaire),
// AVANT tout plafonnement -- sert à déterminer combien de pastilles seraient
// réellement affichées (rendu plafonné à 3, voir GameCard.vue::buildPastilles).
export function rawFactCount(game, side) {
  const { absentPlayers, questionablePlayers } = breakdownSide(game, side)
  const calendar = calendarLabels(game[`${side}_calendar_status`])
  return absentPlayers.length + questionablePlayers.length + calendar.length
}

// Nombre de pastilles réellement rendues pour une équipe -- le plafond de 3
// (règle absolue de §10.4, avec pastille de reste au-delà) ne change jamais,
// seule la hauteur réservée s'adapte à ce nombre à l'échelle de la vue.
export function renderedPastilleCount(game, side) {
  return Math.min(rawFactCount(game, side), 3)
}

export function maxRenderedPastilleCount(games) {
  let max = 0
  for (const game of games) {
    max = Math.max(max, renderedPastilleCount(game, 'home'), renderedPastilleCount(game, 'away'))
  }
  return max
}
