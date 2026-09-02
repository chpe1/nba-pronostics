import { describe, expect, it } from 'vitest'
import { hexToOklab, oklabDistance, oklabToHex, oklabToOklch, oklchToOklab } from './colorSpace'

describe('OKLab <-> sRGB round-trip', () => {
  it('reproduit un hex après un aller-retour hex -> OKLab -> hex, a un pixel pres', () => {
    for (const hex of ['#007A33', '#CE1141', '#0E2240', '#FFFFFF', '#000000', '#98002E']) {
      const roundTripped = oklabToHex(hexToOklab(hex))
      expect(roundTripped).toBe(hex.toUpperCase())
    }
  })
})

describe('OKLab <-> OKLCH round-trip', () => {
  it('conserve L, C, H a travers un aller-retour cartesien <-> cylindrique', () => {
    const lab = hexToOklab('#0E2240')
    const lch = oklabToOklch(lab)
    const backToLab = oklchToOklab(lch)
    expect(backToLab.L).toBeCloseTo(lab.L, 10)
    expect(backToLab.a).toBeCloseTo(lab.a, 10)
    expect(backToLab.b).toBeCloseTo(lab.b, 10)
  })
})

describe('oklabDistance', () => {
  it('vaut 0 pour une couleur comparee a elle-meme', () => {
    expect(oklabDistance('#0E2240', '#0E2240')).toBeCloseTo(0, 10)
  })
})
