import { describe, it, expect, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import DivergentGauge from './DivergentGauge.vue'

// jsdom n'implémente pas requestAnimationFrame (vérifié : `typeof window.requestAnimationFrame`
// vaut `undefined` sur jsdom 30 nu -- Vitest ne le polyfille pas non plus, sa liste de globales
// DOM se contente de RECOPIER ce que jsdom expose). Sans ce stub, le montage du composant
// lèverait -- `requestAnimationFrame` n'est appelé QUE dans onMounted, jamais ailleurs. Contrôlé
// (pas un simple retour immédiat) pour pouvoir observer l'état "avant le cycle d'animation"
// (les deux barres à scaleX(0), départ du centre) avant de déclencher explicitement le cycle.
function stubRequestAnimationFrame() {
  const pending = []
  vi.stubGlobal('requestAnimationFrame', (callback) => {
    pending.push(callback)
    return pending.length
  })
  return {
    flush() {
      const callbacks = pending.splice(0)
      callbacks.forEach((callback) => callback(0))
    },
  }
}

function baseProps(overrides = {}) {
  return {
    homeNote: 50,
    awayNote: 50,
    homeTeamAbbreviation: 'BOS',
    awayTeamAbbreviation: 'LAL',
    thresholdHigh: 20,
    ...overrides,
  }
}

// Marqueurs repris tels quels de l'ancien DivergentGauge.test.js (lecture par regex) : la barre
// `origin-left` est celle du domicile (déport à droite), `origin-right` celle de l'extérieur
// (déport à gauche) -- voir le commentaire de spread dans DivergentGauge.vue.
function homeBar(wrapper) {
  return wrapper.find('.origin-left')
}
function awayBar(wrapper) {
  return wrapper.find('.origin-right')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('DivergentGauge.vue -- montage réel (@vue/test-utils + jsdom)', () => {
  it('porte role="img" et un aria-label calculé quand une équipe est favorite', () => {
    stubRequestAnimationFrame()
    const wrapper = mount(DivergentGauge, {
      props: baseProps({ homeNote: 70, awayNote: 50 }), // spread = 20
    })
    expect(wrapper.attributes('role')).toBe('img')
    expect(wrapper.attributes('aria-label')).toBe('Écart de 20.0 points en faveur de BOS')
  })

  it('aria-label dit "aucun écart" quand les deux notes sont égales', () => {
    stubRequestAnimationFrame()
    const wrapper = mount(DivergentGauge, { props: baseProps() }) // spread = 0
    expect(wrapper.attributes('aria-label')).toBe('Aucun écart entre les deux équipes')
  })

  // Même invariant que l'ancien DivergentGauge.test.js (lecture par regex du source), vérifié ici
  // sur le DOM réellement monté plutôt que sur le texte du fichier : les deux classes doivent
  // coexister sur chaque barre pour que le mécanisme purement CSS de prefers-reduced-motion
  // fonctionne (§13 design-v1.md) -- transition-transform produit l'animation quand la préférence
  // est inactive, motion-reduce:transition-none l'annule quand elle est active. Ne prouve pas plus
  // que l'ancien test qu'un vrai navigateur avec la préférence active supprime effectivement la
  // transition à l'écran (jsdom n'évalue pas les media queries) -- seule la recette visuelle réelle
  // le confirme, voir docs/design-v1.md §13.
  it('porte transition-transform ET motion-reduce:transition-none sur les deux barres', () => {
    stubRequestAnimationFrame()
    const wrapper = mount(DivergentGauge, { props: baseProps() })
    for (const bar of [homeBar(wrapper), awayBar(wrapper)]) {
      expect(bar.classes()).toContain('transition-transform')
      expect(bar.classes()).toContain('motion-reduce:transition-none')
    }
  })

  describe('régression du 2026-09-01 -- bg-accent-text vs bg-neutral selon `muted`', () => {
    it('porte bg-accent-text sur les deux barres quand muted vaut false (défaut)', () => {
      stubRequestAnimationFrame()
      const wrapper = mount(DivergentGauge, { props: baseProps() })
      expect(homeBar(wrapper).classes()).toContain('bg-accent-text')
      expect(homeBar(wrapper).classes()).not.toContain('bg-neutral')
      expect(awayBar(wrapper).classes()).toContain('bg-accent-text')
      expect(awayBar(wrapper).classes()).not.toContain('bg-neutral')
    })

    it('porte bg-neutral sur les deux barres quand muted vaut true -- jamais bg-accent-text', () => {
      stubRequestAnimationFrame()
      const wrapper = mount(DivergentGauge, { props: baseProps({ muted: true }) })
      expect(homeBar(wrapper).classes()).toContain('bg-neutral')
      expect(homeBar(wrapper).classes()).not.toContain('bg-accent-text')
      expect(awayBar(wrapper).classes()).toContain('bg-neutral')
      expect(awayBar(wrapper).classes()).not.toContain('bg-accent-text')
    })
  })

  describe('transform après le cycle d\'animation (depuis le centre, §13 design-v1.md)', () => {
    it('les deux barres démarrent à scaleX(0) avant le cycle de montage (départ du centre)', () => {
      stubRequestAnimationFrame()
      const wrapper = mount(DivergentGauge, { props: baseProps({ homeNote: 70, awayNote: 50 }) })
      expect(homeBar(wrapper).attributes('style')).toContain('scaleX(0)')
      expect(awayBar(wrapper).attributes('style')).toContain('scaleX(0)')
    })

    it('domicile favori : la barre origin-left atteint scaleX(1), origin-right reste à 0', async () => {
      const raf = stubRequestAnimationFrame()
      const wrapper = mount(DivergentGauge, { props: baseProps({ homeNote: 70, awayNote: 50 }) }) // spread = 20 = thresholdHigh -> offset = 1
      raf.flush()
      await nextTick()
      expect(homeBar(wrapper).attributes('style')).toContain('scaleX(1)')
      expect(awayBar(wrapper).attributes('style')).toContain('scaleX(0)')
    })

    it('extérieur favori : la barre origin-right atteint scaleX(1), origin-left reste à 0', async () => {
      const raf = stubRequestAnimationFrame()
      const wrapper = mount(DivergentGauge, { props: baseProps({ homeNote: 40, awayNote: 60 }) }) // spread = -20 -> offset = -1
      raf.flush()
      await nextTick()
      expect(awayBar(wrapper).attributes('style')).toContain('scaleX(1)')
      expect(homeBar(wrapper).attributes('style')).toContain('scaleX(0)')
    })

    it('écart partiel : le déport reflète le ratio spread/thresholdHigh, pas seulement 0 ou 1', async () => {
      const raf = stubRequestAnimationFrame()
      const wrapper = mount(DivergentGauge, { props: baseProps({ homeNote: 55, awayNote: 50, thresholdHigh: 20 }) }) // spread = 5 -> offset = 0.25
      raf.flush()
      await nextTick()
      expect(homeBar(wrapper).attributes('style')).toContain('scaleX(0.25)')
    })
  })
})
