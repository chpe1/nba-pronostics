// Logique PURE de l'écran d'import d'effectif (Décision d'architecture n°39, étape 5) : verdicts sur les
// lignes du fichier sans correspondance, et ce qu'ils autorisent. Isolée du rendu pour rester testable
// sans DOM (même principe que utils/gauge.js).
//
// État d'un verdict, par ligne du fichier (clé : nom tel qu'écrit dans le fichier) :
//   { kind: null | 'recruit' | 'same_player', playerId: null | number }
// Aucun verdict n'est jamais présélectionné : `emptyVerdicts` part toujours de { kind: null }.

export function emptyVerdicts(rows) {
  const verdicts = {}
  for (const row of rows) {
    verdicts[row.name] = { kind: null, playerId: null }
  }
  return verdicts
}

// Une ligne est tranchée si elle est « recrue », ou « même joueur » AVEC un joueur choisi : le simple
// choix du bouton « même joueur que… » sans sélecteur renseigné ne vaut pas verdict.
export function hasVerdict(verdict) {
  if (!verdict) return false
  if (verdict.kind === 'recruit') return true
  return verdict.kind === 'same_player' && verdict.playerId !== null && verdict.playerId !== undefined
}

export function unresolvedRows(rows, verdicts) {
  return rows.filter((row) => !hasVerdict(verdicts[row.name]))
}

// Identifiants des joueurs désignés par une association : présents dans le fichier, donc jamais détachables.
export function associatedPlayerIds(verdicts) {
  const ids = new Set()
  for (const verdict of Object.values(verdicts)) {
    if (verdict.kind === 'same_player' && hasVerdict(verdict)) ids.add(verdict.playerId)
  }
  return ids
}

// Pourquoi le détachement est impossible, ou null s'il est possible. Deux causes, qui s'additionnent :
// des lignes sans verdict, des lignes du fichier en erreur.
export function detachmentBlockReasons({ unresolvedCount, errorCount }) {
  const reasons = []
  if (unresolvedCount > 0) {
    reasons.push(
      `${unresolvedCount} ligne(s) du fichier sans correspondance n'ont pas de verdict : un joueur absent du fichier ` +
        `ne peut être détaché que si chacune de ces lignes a été tranchée (elle pourrait être ce même joueur, écrit autrement).`,
    )
  }
  if (errorCount > 0) {
    reasons.push(
      `${errorCount} ligne(s) du fichier sont en erreur : un nom illisible pourrait être un joueur « absent » à tort. ` +
        `Corrigez le fichier, puis refaites l'aperçu.`,
    )
  }
  return reasons
}

// Corps des verdicts envoyé à la confirmation (champ `verdicts`, JSON) : uniquement les lignes tranchées.
export function buildVerdictPayload(rows, verdicts) {
  const payload = []
  for (const row of rows) {
    const verdict = verdicts[row.name]
    if (!hasVerdict(verdict)) continue
    if (verdict.kind === 'recruit') {
      payload.push({ file_name: row.name, verdict: 'recruit' })
    } else {
      payload.push({ file_name: row.name, verdict: 'same_player', player_id: verdict.playerId })
    }
  }
  return payload
}

export function confirmLabel(detachCount) {
  if (detachCount <= 0) return "Confirmer l'import"
  return `Confirmer et détacher ${detachCount} joueur${detachCount > 1 ? 's' : ''}`
}

// Regroupe les joueurs à détacher par équipe (ordre alphabétique des abréviations, puis des noms).
export function groupByTeam(players) {
  const groups = new Map()
  for (const player of players) {
    if (!groups.has(player.team_abbreviation)) groups.set(player.team_abbreviation, [])
    groups.get(player.team_abbreviation).push(player)
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([team, items]) => ({ team, players: [...items].sort((x, y) => x.name.localeCompare(y.name)) }))
}
