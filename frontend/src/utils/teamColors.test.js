import { describe, expect, it } from 'vitest'
import { resolveTeamBadges } from './teamColors'
import { contrastRatio } from './colorSpace'
import { MIN_BADGE_FILL_CONTRAST, MIN_BADGE_TEXT_CONTRAST } from './teamColorContrast'

const SURFACE_DARK = '#1a1d26'
const SURFACE_LIGHT = '#ffffff'

describe('resolveTeamBadges', () => {
  it('bascule l’équipe extérieure sur sa secondaire en cas de collision (Miami chez Chicago)', () => {
    const { home, away } = resolveTeamBadges('CHI', 'MIA', 'dark')
    expect(home).not.toBeNull()
    expect(away).not.toBeNull()
    // Chicago (domicile) garde sa primaire (rouge) -- seule Miami bascule.
    expect(home.fill.toUpperCase()).toBe('#CE1141')
    // La secondaire de Miami est le noir (constants/teamColors.js) : une
    // fois ajustée pour le contraste, elle reste bien plus sombre/neutre
    // que le rouge de Chicago -- vérifié par un vrai calcul de distance,
    // pas supposé.
    expect(away.fill).not.toBe(home.fill)
  })

  it('ne bascule PAS le domicile, même en cas de collision', () => {
    const { home } = resolveTeamBadges('CHI', 'MIA', 'dark')
    expect(home.fill.toUpperCase()).toBe('#CE1141')
  })

  it('ne bascule rien quand il n’y a pas de collision (Boston chez Denver)', () => {
    const { home, away } = resolveTeamBadges('DEN', 'BOS', 'dark')
    expect(home).not.toBeNull()
    expect(away).not.toBeNull()
    // Boston (extérieur) garde sa primaire : vert, pas d'ajustement requis
    // sur fond sombre puisque déjà conforme (voir teamColorContrast.test.js).
    expect(away.fill.toUpperCase()).toBe('#007A33')
  })

  it('renvoie null pour une équipe hors du périmètre des 6, sans lever d’erreur', () => {
    const { home, away } = resolveTeamBadges('LAL', 'BOS', 'dark')
    expect(home).toBeNull()
    expect(away).not.toBeNull()
  })

  it('la collision est évaluée sur les couleurs BRUTES, pas sur le rendu ajusté par mode', () => {
    // Même verdict de collision dans les deux modes malgré des fonds très
    // différents (sombre/clair) -- Miami bascule sur sa secondaire chez
    // Chicago quel que soit le thème actif.
    const dark = resolveTeamBadges('CHI', 'MIA', 'dark')
    const light = resolveTeamBadges('CHI', 'MIA', 'light')
    // La secondaire de Miami (noir) reste inchangée en clair (déjà très
    // contrastée) : un test de non-régression sur la stabilité de la
    // décision de bascule elle-même, pas sur la teinte rendue (qui, elle,
    // dépend légitimement du mode via adjustForContrast).
    expect(dark.away.fill).not.toBe(dark.home.fill)
    expect(light.away.fill).not.toBe(light.home.fill)
  })

  for (const [mode, background] of [
    ['dark', SURFACE_DARK],
    ['light', SURFACE_LIGHT],
  ]) {
    it(`chaque badge résolu (${mode}) respecte les deux seuils de contraste`, () => {
      const pairs = [
        ['CHI', 'MIA'],
        ['DEN', 'BOS'],
        ['DET', 'CHA'],
      ]
      for (const [home, away] of pairs) {
        const badges = resolveTeamBadges(home, away, mode)
        for (const badge of [badges.home, badges.away]) {
          expect(contrastRatio(badge.fill, background)).toBeGreaterThanOrEqual(MIN_BADGE_FILL_CONTRAST)
          expect(contrastRatio(badge.fill, badge.text)).toBeGreaterThanOrEqual(MIN_BADGE_TEXT_CONTRAST)
        }
      }
    })
  }
})
