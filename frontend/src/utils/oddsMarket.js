// Calculs de marché à partir des cotes décimales déjà en base (probabilité implicite, marge du
// bookmaker, probabilités sans marge, meilleure cote) -- PUREMENT dérivés, jamais stockés, jamais
// envoyés au serveur. Isolés du rendu pour rester testables sans DOM (même patron que utils/gauge.js).
// AUCUN calcul de value ici : le moteur n'a pas encore de probabilité à comparer (2026-10-24).

/** Probabilité implicite d'une cote décimale (l'inverse). `null` si la cote est absente. */
export function impliedProbability(odds) {
  if (odds === null || odds === undefined) return null
  return 1 / odds
}

/**
 * Marge du bookmaker = somme des deux probabilités implicites - 1, en POURCENTAGE (le signe dit
 * lequel des deux bookmakers prend le plus). `null` si l'une des deux cotes manque -- la marge
 * suppose les deux côtés du même marché chez la même source.
 */
export function bookmakerMarginPct(probHome, probAway) {
  if (probHome === null || probAway === null) return null
  return (probHome + probAway - 1) * 100
}

/** Probabilités normalisées (la marge retirée, proportionnellement), pour une même source. */
export function noMarginProbabilities(probHome, probAway) {
  if (probHome === null || probAway === null) return { home: null, away: null }
  const total = probHome + probAway
  if (total === 0) return { home: null, away: null }
  return { home: probHome / total, away: probAway / total }
}

/**
 * Lit un texte saisi au clavier comme une cote (virgule OU point décimal) -- calcul d'AFFICHAGE
 * seulement (aperçu en direct pendant la saisie) : la validation qui compte, celle qui décide ce qui
 * est écrit en base, reste entièrement côté serveur (app/services/odds.py::parse_odds_value). Une
 * entrée illisible donne simplement `null` (pas encore une cote), jamais une erreur ici.
 */
export function parseOddsInput(raw) {
  if (raw === null || raw === undefined) return null
  const trimmed = String(raw).trim()
  if (trimmed === '') return null
  const value = Number(trimmed.replace(',', '.'))
  return Number.isFinite(value) ? value : null
}

/** Formate une cote stockée (toujours un point) en écriture française (virgule), 2 décimales. */
export function formatOddsFr(value) {
  if (value === null || value === undefined) return ''
  return value.toFixed(2).replace('.', ',')
}

/**
 * Meilleure cote d'un côté entre deux sources -- indépendamment pour domicile et extérieur : rien
 * n'oblige à parier les deux côtés chez le même bookmaker. `null` si aucune des deux n'a de valeur.
 */
export function bestOdds(a, b) {
  if (a === null || a === undefined) return b ?? null
  if (b === null || b === undefined) return a
  return Math.max(a, b)
}
