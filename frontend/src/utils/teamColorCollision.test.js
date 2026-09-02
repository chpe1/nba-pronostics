import { describe, expect, it } from 'vitest'
import { COLLISION_THRESHOLD_OKLAB, haveColorCollision, oklabColorDistance } from './teamColorCollision'

describe('oklabColorDistance', () => {
  it('vaut 0 pour deux couleurs identiques', () => {
    expect(oklabColorDistance('#CE1141', '#CE1141')).toBeCloseTo(0, 10)
  })

  it('est symétrique', () => {
    expect(oklabColorDistance('#98002E', '#CE1141')).toBeCloseTo(oklabColorDistance('#CE1141', '#98002E'), 10)
  })
})

describe('haveColorCollision', () => {
  // Seuil recalibré le 2026-09-02 (0,15 -> 0,03) après un changement
  // d'objectif, pas un réglage plus fin du même objectif -- voir
  // docs/design-v1.md §5.7, "Recadrage". Miami/Chicago (ΔE_OK brut ≈ 0,12,
  // le cas rapporté en recette à l'origine du chantier) n'est PLUS une
  // collision au nouveau seuil : deux rouges reconnaissables l'un de
  // l'autre, le tricode fait le reste. Ne pas "corriger" ce test dans
  // l'autre sens sans revoir §5.7 d'abord.
  it('ne détecte plus Miami/Chicago comme une collision au nouveau seuil', () => {
    expect(haveColorCollision('#CE1141', '#98002E')).toBe(false)
  })

  it('ne détecte plus Détroit/Denver (marines proches mais distincts, ΔE_OK ≈ 0,067)', () => {
    expect(haveColorCollision('#002D62', '#0E2240')).toBe(false)
  })

  it('détecte deux teintes strictement identiques (ex. plusieurs équipes au même rouge officiel)', () => {
    expect(haveColorCollision('#CE1141', '#CE1141')).toBe(true)
  })

  it('détecte deux teintes quasi identiques, sous le seuil sans y être égales', () => {
    // Deux rouges à peine distincts (ΔE_OK ≈ 0,026, mesuré -- sous le
    // seuil de 0,03 mais pas nul).
    expect(oklabColorDistance('#CE1141', '#C21C4A')).toBeCloseTo(0.026, 2)
    expect(haveColorCollision('#CE1141', '#C21C4A')).toBe(true)
  })

  it('ne détecte pas de collision entre un vert et un rouge manifestement distincts', () => {
    expect(haveColorCollision('#007A33', '#CE1141')).toBe(false)
  })

  it('respecte le seuil fourni explicitement plutôt que la constante par défaut', () => {
    // Deux teintes strictement identiques collisionnent à n'importe quel
    // seuil positif, y compris un seuil resserré à l'extrême.
    expect(haveColorCollision('#CE1141', '#CE1141', 0.001)).toBe(true)
    // ... mais pas deux teintes seulement proches (Miami/Chicago) sous un
    // seuil aussi serré.
    expect(haveColorCollision('#CE1141', '#98002E', 0.001)).toBe(false)
  })

  it('le seuil par défaut est bien 0,03', () => {
    expect(COLLISION_THRESHOLD_OKLAB).toBe(0.03)
  })
})
