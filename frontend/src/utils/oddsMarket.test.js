import { describe, it, expect } from 'vitest'
import {
  impliedProbability,
  bookmakerMarginPct,
  noMarginProbabilities,
  bestOdds,
  parseOddsInput,
  formatOddsFr,
} from './oddsMarket'

describe('impliedProbability', () => {
  it("vaut l'inverse de la cote", () => {
    expect(impliedProbability(2)).toBeCloseTo(0.5)
    expect(impliedProbability(1.85)).toBeCloseTo(0.5405, 4)
  })
  it('est nulle sans cote', () => {
    expect(impliedProbability(null)).toBeNull()
    expect(impliedProbability(undefined)).toBeNull()
  })
})

describe('bookmakerMarginPct', () => {
  it('est positive quand la somme dépasse 1 (cas réel)', () => {
    // Winamax 1.85 / 1.95 -> 0.5405 + 0.5128 = 1.0533 -> marge 5.33%
    const margin = bookmakerMarginPct(impliedProbability(1.85), impliedProbability(1.95))
    expect(margin).toBeCloseTo(5.33, 1)
  })
  it('est nulle (valeur manquante) si un seul côté est renseigné', () => {
    expect(bookmakerMarginPct(0.5, null)).toBeNull()
    expect(bookmakerMarginPct(null, 0.5)).toBeNull()
  })
  it('vaut 0 pour un marché sans marge (cotes justes)', () => {
    expect(bookmakerMarginPct(0.5, 0.5)).toBeCloseTo(0)
  })
})

describe('noMarginProbabilities', () => {
  it('retire la marge proportionnellement', () => {
    const { home, away } = noMarginProbabilities(0.6, 0.5)
    expect(home + away).toBeCloseTo(1)
    expect(home).toBeCloseTo(0.6 / 1.1)
    expect(away).toBeCloseTo(0.5 / 1.1)
  })
  it('est nulle si une probabilité manque', () => {
    expect(noMarginProbabilities(null, 0.5)).toEqual({ home: null, away: null })
  })
})

describe('bestOdds', () => {
  it('prend la plus haute des deux (meilleure pour le parieur)', () => {
    expect(bestOdds(1.85, 1.90)).toBe(1.90)
    expect(bestOdds(2.10, 1.95)).toBe(2.10)
  })
  it("retombe sur l'unique valeur disponible", () => {
    expect(bestOdds(1.85, null)).toBe(1.85)
    expect(bestOdds(null, 1.90)).toBe(1.90)
  })
  it('est nulle si aucune des deux source n’a de valeur', () => {
    expect(bestOdds(null, null)).toBeNull()
  })
})

describe('parseOddsInput', () => {
  it('lit la virgule française et le point', () => {
    expect(parseOddsInput('1,85')).toBeCloseTo(1.85)
    expect(parseOddsInput('1.85')).toBeCloseTo(1.85)
  })
  it('est nul pour un champ vide ou illisible', () => {
    expect(parseOddsInput('')).toBeNull()
    expect(parseOddsInput('   ')).toBeNull()
    expect(parseOddsInput(null)).toBeNull()
    expect(parseOddsInput('abc')).toBeNull()
  })
})

describe('formatOddsFr', () => {
  it('affiche deux décimales avec une virgule', () => {
    expect(formatOddsFr(1.8)).toBe('1,80')
    expect(formatOddsFr(1.85)).toBe('1,85')
  })
  it('est vide sans valeur', () => {
    expect(formatOddsFr(null)).toBe('')
  })
})
