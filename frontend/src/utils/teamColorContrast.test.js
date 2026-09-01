import { describe, expect, it } from 'vitest'
import { adjustForContrast, contrastRatio, MIN_RAIL_CONTRAST } from './teamColorContrast'
import { TEAM_COLORS } from '@/constants/teamColors'

const SURFACE_DARK = '#1a1d26'
const SURFACE_LIGHT = '#ffffff'

describe('contrastRatio', () => {
  it('donne 21:1 entre noir et blanc (cas de référence WCAG)', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 0)
  })

  it('est symétrique', () => {
    expect(contrastRatio('#123456', '#abcdef')).toBeCloseTo(contrastRatio('#abcdef', '#123456'), 10)
  })

  it('donne 1:1 pour deux couleurs identiques', () => {
    expect(contrastRatio('#f97316', '#f97316')).toBeCloseTo(1, 5)
  })
})

describe('adjustForContrast', () => {
  it("laisse une couleur déjà conforme inchangée (n'ajuste jamais sans raison)", () => {
    expect(adjustForContrast('#ffffff', '#000000')).toBe('#ffffff')
  })

  it('éclaircit une couleur trop sombre pour un fond sombre', () => {
    const adjusted = adjustForContrast('#0e2240', SURFACE_DARK)
    expect(contrastRatio(adjusted, SURFACE_DARK)).toBeGreaterThanOrEqual(MIN_RAIL_CONTRAST)
  })

  it('assombrit une couleur trop claire pour un fond clair', () => {
    const adjusted = adjustForContrast('#fdba74', SURFACE_LIGHT)
    expect(contrastRatio(adjusted, SURFACE_LIGHT)).toBeGreaterThanOrEqual(MIN_RAIL_CONTRAST)
  })

  it('ne modifie jamais la teinte (H) ni la saturation (S), seulement la luminosité', () => {
    // #0E2240 (Denver) sur fond sombre a besoin d'être éclairci -- vérifie
    // que le résultat reste dans la même famille de teinte (composante
    // bleue toujours dominante), pas un ajustement qui aurait dérivé.
    const adjusted = adjustForContrast('#0e2240', SURFACE_DARK)
    const r = parseInt(adjusted.slice(1, 3), 16)
    const g = parseInt(adjusted.slice(3, 5), 16)
    const b = parseInt(adjusted.slice(5, 7), 16)
    expect(b).toBeGreaterThan(r)
    expect(b).toBeGreaterThan(g)
  })

  for (const [abbreviation, hex] of Object.entries(TEAM_COLORS)) {
    it(`${abbreviation} atteint ${MIN_RAIL_CONTRAST}:1 sur bg-surface sombre`, () => {
      const adjusted = adjustForContrast(hex, SURFACE_DARK)
      expect(contrastRatio(adjusted, SURFACE_DARK)).toBeGreaterThanOrEqual(MIN_RAIL_CONTRAST)
    })

    it(`${abbreviation} atteint ${MIN_RAIL_CONTRAST}:1 sur bg-surface clair`, () => {
      const adjusted = adjustForContrast(hex, SURFACE_LIGHT)
      expect(contrastRatio(adjusted, SURFACE_LIGHT)).toBeGreaterThanOrEqual(MIN_RAIL_CONTRAST)
    })
  }
})
