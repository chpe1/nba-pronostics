import { describe, it, expect } from 'vitest'
import { joinTeams, noteBasis } from './noteBasis'

const bd = (homeEarly, awayEarly) => ({ home: { in_early_season: homeEarly }, away: { in_early_season: awayEarly } })

describe('noteBasis', () => {
  it('classe chaque équipe selon sa mesure, dans l\'ordre de la carte (extérieur puis domicile)', () => {
    expect(noteBasis(bd(true, true), 'DET', 'BOS')).toEqual({ known: true, current: [], previous: ['BOS', 'DET'], mixed: false })
    expect(noteBasis(bd(false, false), 'DET', 'BOS')).toEqual({ known: true, current: ['BOS', 'DET'], previous: [], mixed: false })
    expect(noteBasis(bd(false, true), 'DET', 'BOS')).toEqual({ known: true, current: ['DET'], previous: ['BOS'], mixed: true })
    expect(noteBasis(bd(true, false), 'DET', 'BOS')).toEqual({ known: true, current: ['BOS'], previous: ['DET'], mixed: true })
  })

  it('« bases différentes » exactement quand une équipe seulement a basculé', () => {
    for (const [h, a, mixed] of [[true, true, false], [false, false, false], [true, false, true], [false, true, true]]) {
      expect(noteBasis(bd(h, a), 'DET', 'BOS').mixed).toBe(mixed)
    }
  })

  it('ne devine pas : information absente ou partielle -> known false', () => {
    expect(noteBasis(undefined, 'DET', 'BOS').known).toBe(false)
    expect(noteBasis({}, 'DET', 'BOS').known).toBe(false)
    expect(noteBasis(bd(true, undefined), 'DET', 'BOS').known).toBe(false)
    expect(noteBasis(bd('oui', false), 'DET', 'BOS').known).toBe(false)
  })

  it('joinTeams', () => {
    expect(joinTeams(['ATL'])).toBe('ATL')
    expect(joinTeams(['ATL', 'LAL'])).toBe('ATL et LAL')
  })
})
