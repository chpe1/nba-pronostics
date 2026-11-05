// Mise en forme du relevé automatique des cotes (the-odds-api.com). Les instants arrivent en ISO 8601 avec « Z »
// (UTC) : on les affiche dans le fuseau du NAVIGATEUR (jamais lus comme une heure murale, limitation n°35).

export function formatLocalTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}

export function formatLocalDateTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' })} ${formatLocalTime(iso)}`
}

export const COLLECTION_LABELS = { manuel: 'manuel', api: 'auto' }

// Un appel qui ne lit aucune cote : la relecture GRATUITE du solde de crédits (0 crédit consommé, aucun match
// renvoyé). Un vrai relevé consomme toujours au moins un crédit.
export function isBalanceCheck(run) {
  return run.http_status === 200 && run.events_returned === 0 && run.credits_used === 0
}

export const UNMATCHED_REASONS = {
  unknown_team: "nom d'équipe absent de la table de correspondance",
  not_in_database: 'aucun match en base ce jour-là avec ces deux équipes',
  home_away_reversed: 'match en base avec domicile et extérieur inversés',
  bad_start_time: "heure de début illisible",
  duplicate_event: "deuxième événement de l'API pour le même match",
}
export const IGNORED_REASONS = { finished: 'terminé', postponed: 'reporté', started: 'coup d\'envoi passé' }
export const NO_ODDS_REASONS = {
  not_in_response: "marché pas encore ouvert chez l'API",
  no_bookmaker: 'aucun bookmaker pour ce match',
}
export const ANOMALY_REASONS = {
  unknown_market: 'marché inconnu',
  outcome_name: "issue qui n'est ni l'équipe à domicile ni celle à l'extérieur",
  bad_price: 'cote absente ou invalide',
  bad_source: 'identifiant de bookmaker inexploitable',
}

export const reasonLabel = (table, reason) => table[reason] ?? reason
