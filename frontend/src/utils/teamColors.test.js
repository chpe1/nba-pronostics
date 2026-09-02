import { describe, expect, it } from 'vitest'
import { resolveTeamBadges } from './teamColors'
import { contrastRatio } from './colorSpace'
import { MIN_BADGE_FILL_CONTRAST, MIN_BADGE_TEXT_CONTRAST } from './teamColorContrast'

const SURFACE_DARK = '#1a1d26'
const SURFACE_LIGHT = '#ffffff'

describe('resolveTeamBadges', () => {
  // Miami-Chicago (ΔE_OK brut ≈ 0,12) collisionnait sous l'ancien seuil
  // (0,15, calé sur "identification absolue", abandonnée le 2026-09-02).
  // Sous le seuil retenu (0,03, calé sur "perceptibles comme deux" --
  // §5.7), ce n'est PLUS une collision : les deux restent des rouges
  // reconnaissables l'un de l'autre, le tricode fait le reste. Régression
  // intentionnelle, pas un oubli -- ne pas "corriger" ce test en sens
  // inverse sans revoir §5.7 d'abord.
  it('ne bascule plus Miami chez Chicago (rouges distincts, plus une collision au nouveau seuil)', () => {
    const { home, away } = resolveTeamBadges('CHI', 'MIA', 'dark')
    expect(home.fill.toUpperCase()).toBe('#CE1141')
    expect(away.fill.toUpperCase()).toBe('#BE354C') // primaire de Miami, ajustée -- jamais sa secondaire
  })

  // Aucune paire parmi les 6 équipes actuelles ne collisionne au nouveau
  // seuil (la plus proche, Détroit-Denver, est à 0,067 -- plus de 2x le
  // seuil). Le mécanisme de bascule est donc exercé ici avec une équipe
  // contre elle-même (ΔE_OK = 0 par construction) : cas synthétique,
  // jamais rencontré en vrai calendrier NBA, mais la seule façon de
  // vérifier que la bascule se déclenche encore correctement quand une
  // collision existe réellement.
  it('bascule l’équipe extérieure sur sa secondaire quand une collision existe (cas synthétique : équipe contre elle-même)', () => {
    const { home, away } = resolveTeamBadges('CHI', 'CHI', 'dark')
    expect(home.fill.toUpperCase()).toBe('#CE1141') // domicile : toujours la primaire
    expect(away.fill).not.toBe(home.fill) // extérieure : a basculé sur sa secondaire (noir, ajusté)
  })

  it('ne bascule JAMAIS le domicile, même en cas de collision', () => {
    const { home } = resolveTeamBadges('CHI', 'CHI', 'dark')
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

  it('renvoie null pour une abréviation inconnue de TEAM_COLORS, sans lever d’erreur', () => {
    // 'ZZZ' : aucune équipe NBA, ne peut jamais exister dans TEAM_COLORS
    // (30 équipes désormais couvertes, contrairement à LAL utilisé ici
    // avant l'extension du 2026-09-02).
    const { home, away } = resolveTeamBadges('ZZZ', 'BOS', 'dark')
    expect(home).toBeNull()
    expect(away).not.toBeNull()
  })

  it('la collision est évaluée sur les couleurs BRUTES, pas sur le rendu ajusté par mode', () => {
    // Cas synthétique (équipe contre elle-même, voir plus haut) : même
    // verdict de collision dans les deux modes malgré des fonds très
    // différents (sombre/clair) -- la bascule se déclenche quel que soit
    // le thème actif, jamais recalculée à partir du rendu.
    const dark = resolveTeamBadges('CHI', 'CHI', 'dark')
    const light = resolveTeamBadges('CHI', 'CHI', 'light')
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
        ['CHI', 'CHI'],
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
