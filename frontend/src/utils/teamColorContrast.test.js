import { describe, expect, it } from 'vitest'
import { adjustForContrast, MIN_BADGE_FILL_CONTRAST, MIN_BADGE_TEXT_CONTRAST, pickBadgeTextColor } from './teamColorContrast'
import { contrastRatio, hexToOklab, oklabToOklch } from './colorSpace'
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

describe('adjustForContrast (OKLCH, teinte constante)', () => {
  it("laisse une couleur déjà conforme inchangée (n'ajuste jamais sans raison)", () => {
    expect(adjustForContrast('#ffffff', '#000000')).toBe('#ffffff')
  })

  it('éclaircit une couleur trop sombre pour un fond sombre', () => {
    const adjusted = adjustForContrast('#0e2240', SURFACE_DARK)
    expect(contrastRatio(adjusted, SURFACE_DARK)).toBeGreaterThanOrEqual(MIN_BADGE_FILL_CONTRAST)
  })

  it('assombrit une couleur trop claire pour un fond clair', () => {
    const adjusted = adjustForContrast('#fdba74', SURFACE_LIGHT)
    expect(contrastRatio(adjusted, SURFACE_LIGHT)).toBeGreaterThanOrEqual(MIN_BADGE_FILL_CONTRAST)
  })

  it('conserve la teinte OKLCH (H) au degré près (méthode : constante par construction)', () => {
    const { L, a, b } = hexToOklab('#0e2240')
    const { H: hueBefore } = oklabToOklch({ L, a, b })
    const adjusted = adjustForContrast('#0e2240', SURFACE_DARK)
    const after = hexToOklab(adjusted)
    const { H: hueAfter } = oklabToOklch(after)
    expect(hueAfter).toBeCloseTo(hueBefore, 0)
  })

  it('ne réduit jamais la chroma quand ce n’est pas nécessaire (Denver reste en gamut)', () => {
    const { L, a, b } = hexToOklab('#0e2240')
    const { C: chromaBefore } = oklabToOklch({ L, a, b })
    const adjusted = adjustForContrast('#0e2240', SURFACE_DARK)
    const after = hexToOklab(adjusted)
    const { C: chromaAfter } = oklabToOklch(after)
    expect(chromaAfter).toBeCloseTo(chromaBefore, 2)
  })

  it('ne bascule jamais vers une teinte différente comme le faisait HSL (Denver ne devient pas un bleu franc)', () => {
    // #2B69C6 était le résultat de l'ancienne méthode HSL, un bleu bien
    // plus saturé/franc que le marine d'origine -- la méthode OKLCH doit
    // rester nettement plus proche de #0E2240 dans l'espace perceptuel.
    const adjusted = adjustForContrast('#0e2240', SURFACE_DARK)
    const distanceToOriginal = Math.hypot(
      ...['L', 'a', 'b'].map((k) => hexToOklab(adjusted)[k] - hexToOklab('#0e2240')[k]),
    )
    const distanceHslResultToOriginal = Math.hypot(
      ...['L', 'a', 'b'].map((k) => hexToOklab('#2b69c6')[k] - hexToOklab('#0e2240')[k]),
    )
    expect(distanceToOriginal).toBeLessThan(distanceHslResultToOriginal)
  })

  for (const [abbreviation, { primary }] of Object.entries(TEAM_COLORS)) {
    it(`${abbreviation} (primaire) atteint ${MIN_BADGE_FILL_CONTRAST}:1 sur bg-surface sombre`, () => {
      const adjusted = adjustForContrast(primary, SURFACE_DARK)
      expect(contrastRatio(adjusted, SURFACE_DARK)).toBeGreaterThanOrEqual(MIN_BADGE_FILL_CONTRAST)
    })

    it(`${abbreviation} (primaire) atteint ${MIN_BADGE_FILL_CONTRAST}:1 sur bg-surface clair`, () => {
      const adjusted = adjustForContrast(primary, SURFACE_LIGHT)
      expect(contrastRatio(adjusted, SURFACE_LIGHT)).toBeGreaterThanOrEqual(MIN_BADGE_FILL_CONTRAST)
    })
  }
})

describe('pickBadgeTextColor', () => {
  it('choisit toujours une couleur qui atteint 4,5:1, pour tout fond de badge (les 30 équipes, primaire et secondaire, deux modes)', () => {
    for (const { primary, secondary } of Object.values(TEAM_COLORS)) {
      for (const raw of [primary, secondary]) {
        for (const background of [SURFACE_DARK, SURFACE_LIGHT]) {
          const fill = adjustForContrast(raw, background)
          const { ratio } = pickBadgeTextColor(fill)
          expect(ratio).toBeGreaterThanOrEqual(MIN_BADGE_TEXT_CONTRAST)
        }
      }
    }
  })

  it('prend le blanc pur sur un fond sombre, le noir pur sur un fond clair (cas simples)', () => {
    expect(pickBadgeTextColor('#000000').color).toBe('#FFFFFF')
    expect(pickBadgeTextColor('#FFFFFF').color).toBe('#000000')
  })

  // Régression du 2026-09-02 (extension à 30 équipes) : les tokens --text
  // de l'app (quasi blanc/quasi noir, pas 0/1 exacts) laissaient un
  // intervalle de luminance de fond ([0,164 ; 0,211]) sans AUCUN choix
  // valide -- découvert sur 7 équipes réelles (ATL, MEM, OKC, ORL, PHI,
  // POR, WAS), jamais sur les 6 de la base de développement (coïncidence,
  // aucune de leurs couleurs n'y tombait). Corrigé en blanc/noir purs,
  // seule paire dont la preuve mathématique ne dépend d'aucune teinte de
  // fond particulière.
  it('atteint 4,5:1 même pour une luminance de fond dans l’ancien intervalle sans solution (ATL, réel)', () => {
    const fill = adjustForContrast('#E03A3E', SURFACE_DARK) // inchangée : déjà conforme à 3:1 brute
    const { ratio } = pickBadgeTextColor(fill)
    expect(ratio).toBeGreaterThanOrEqual(MIN_BADGE_TEXT_CONTRAST)
  })
})
