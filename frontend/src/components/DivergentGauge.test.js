import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// Ce que ce test PEUT affirmer, et ce qu'il NE PEUT PAS affirmer (voir docs/design-v1.md §13
// pour la version consignée) :
//
// - `prefers-reduced-motion` est géré ici entièrement côté CSS (variante Tailwind
//   `motion-reduce:`), jamais en JS -- DivergentGauge.vue ne lit `matchMedia` nulle part, la
//   transition depuis le centre (mounted/rightScale/leftScale) suit exactement le même chemin de
//   code que la préférence soit active ou non. Un test qui monterait le composant (jsdom +
//   @vue/test-utils, ni l'un ni l'autre présents dans ce projet -- vite.config.js fixe
//   `environment: 'node'`, aucun DOM disponible) ne pourrait de toute façon PAS observer l'effet
//   réel de la media query : jsdom n'implémente pas `window.matchMedia` par défaut et n'évalue pas
//   les media features CSS lors du calcul des styles -- ajouter ces dépendances n'aurait donc pas
//   réglé le problème, seulement donné l'illusion d'un test plus complet.
// - Ce test vérifie donc uniquement l'INVARIANT SOURCE que ce mécanisme exige : les deux barres
//   animées portent à la fois `transition-transform` (la classe qui produit l'animation quand la
//   préférence est INACTIVE -- c'est la règle CSS non conditionnelle) et
//   `motion-reduce:transition-none` (la classe qui l'annule quand la préférence est ACTIVE -- une
//   règle sous `@media (prefers-reduced-motion: reduce)`, vérifiée dans le CSS compilé réel avant
//   d'écrire ce test : `transition-property: none` y remplace bien `transition-property: transform`
//   pour le même élément). Un test qui ne vérifierait qu'une des deux classes passerait aussi bien
//   avec une régression sur l'autre -- les deux sont donc affirmées séparément, jamais une seule
//   assertion globale.
// - Ce que ce test NE PROUVE PAS : qu'un vrai navigateur, avec la préférence système réellement
//   activée, supprime effectivement la transition à l'écran. C'est un comportement du moteur de
//   rendu (media query + transitions CSS), pas du code de ce projet -- seule une vérification
//   visuelle réelle (voir recette-design-lot3.md) peut le confirmer.

const componentSource = readFileSync(
  fileURLToPath(new URL('./DivergentGauge.vue', import.meta.url)),
  'utf-8',
)

function classAttrContaining(marker) {
  const pattern = new RegExp(`class="([^"]*\\b${marker}\\b[^"]*)"`)
  const match = componentSource.match(pattern)
  return match ? match[1] : null
}

describe('DivergentGauge.vue -- prefers-reduced-motion (invariant source, voir commentaire ci-dessus)', () => {
  it.each([
    ['barre droite (favori à domicile)', 'origin-left'],
    ['barre gauche (favori à l\'extérieur)', 'origin-right'],
  ])('%s : porte transition-transform ET motion-reduce:transition-none', (_label, marker) => {
    const classAttr = classAttrContaining(marker)
    expect(classAttr, `aucun élément avec la classe "${marker}" trouvé dans DivergentGauge.vue`).not.toBeNull()

    // Cas "préférence inactive" : la classe qui produit réellement l'animation doit être présente.
    expect(classAttr).toContain('transition-transform')
    // Cas "préférence active" : la classe qui l'annule doit être présente sur le MÊME élément --
    // les deux assertions portent sur le même classAttr, jamais deux éléments différents.
    expect(classAttr).toContain('motion-reduce:transition-none')
  })
})
