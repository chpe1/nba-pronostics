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
  it('détecte la collision Miami/Chicago (rouges proches, le cas rapporté en recette)', () => {
    expect(haveColorCollision('#CE1141', '#98002E')).toBe(true)
  })

  it('détecte deux marines très proches (Détroit/Denver)', () => {
    expect(haveColorCollision('#002D62', '#0E2240')).toBe(true)
  })

  it('ne détecte pas de collision entre un vert et un rouge manifestement distincts', () => {
    expect(haveColorCollision('#007A33', '#CE1141')).toBe(false)
  })

  it('respecte le seuil fourni explicitement plutôt que la constante par défaut', () => {
    // Miami/Chicago (~0.12) : collision au seuil par défaut (0.15), plus de
    // collision avec un seuil volontairement resserré à 0.05.
    expect(haveColorCollision('#CE1141', '#98002E', 0.05)).toBe(false)
  })

  it('le seuil par défaut est bien 0,15', () => {
    expect(COLLISION_THRESHOLD_OKLAB).toBe(0.15)
  })
})
