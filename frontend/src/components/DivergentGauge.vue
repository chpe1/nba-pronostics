<script setup>
import { computed, onMounted, ref } from 'vue'
import { computeGaugeOffset } from '@/utils/gauge'

const props = defineProps({
  homeNote: { type: Number, required: true },
  awayNote: { type: Number, required: true },
  homeTeamAbbreviation: { type: String, required: true },
  awayTeamAbbreviation: { type: String, required: true },
  thresholdHigh: { type: Number, required: true },
  // "Jauge réduite" du bandeau vitrine (§9.2) -- même mécanique, juste plus
  // fine, pas un second composant.
  compact: { type: Boolean, default: false },
  // §10.2 : "faible" retire tout accent de la carte -- PAS un 3e code
  // couleur de la barre (elle n'encode déjà pas élevée/modérée, voir plus
  // bas), un simple binaire décidé par l'appelant (GameCard.vue), qui seul
  // connaît le niveau de fiabilité. Défaut false : le bandeau vitrine
  // (ContextBanner.vue) ne passe pas ce prop et garde son traitement propre
  // (§9.2, décision distincte, non concernée par cette règle).
  muted: { type: Boolean, default: false },
})

// spread : positif = domicile favori (même convention que le backend, voir
// app/models/prediction.py) -- déport à droite pour le domicile, à gauche pour
// l'extérieur. Convention purement interne à ce composant, cohérente avec
// l'ordre extérieur (haut) / domicile (bas) déjà utilisé par GameCard.vue :
// lecture de haut en bas = lecture de gauche à droite.
const spread = computed(() => props.homeNote - props.awayNote)
const offset = computed(() => computeGaugeOffset(spread.value, props.thresholdHigh))

// Anime depuis le centre au montage plutôt que de démarrer directement à la
// valeur finale -- prefers-reduced-motion neutralise la transition CSS
// (motion-reduce:transition-none), donc le même mécanisme affiche la valeur
// finale sans étape intermédiaire visible dans ce cas, sans branche JS dédiée.
const mounted = ref(false)
onMounted(() => {
  requestAnimationFrame(() => {
    mounted.value = true
  })
})

const rightScale = computed(() => (mounted.value && offset.value > 0 ? offset.value : 0))
const leftScale = computed(() => (mounted.value && offset.value < 0 ? -offset.value : 0))

const favoredAbbreviation = computed(() =>
  offset.value === 0 ? null : offset.value > 0 ? props.homeTeamAbbreviation : props.awayTeamAbbreviation,
)
const ariaLabel = computed(() => {
  const gap = Math.abs(spread.value).toFixed(1)
  return favoredAbbreviation.value
    ? `Écart de ${gap} points en faveur de ${favoredAbbreviation.value}`
    : 'Aucun écart entre les deux équipes'
})
</script>

<template>
  <div
    class="relative w-full overflow-hidden rounded-full bg-surface-sunken"
    :class="compact ? 'h-1' : 'h-2'"
    role="img"
    :aria-label="ariaLabel"
  >
    <!-- `bg-accent-text`, PAS `bg-accent` : c'est l'accent DU MODE (§5.3). En sombre les
         deux tokens valent le même #F97316, rien ne bouge ; en clair, `--accent-fill`
         (#F97316) ne donnait que 2,33:1 contre la piste #E8EAEF, sous les 3:1 d'un objet
         non textuel (WCAG 1.4.11) -- et aucune piste PLUS CLAIRE ne pouvait y remédier, le
         blanc lui-même plafonnant à 2,80:1 contre cet orange. `--accent-text` (#C2410C)
         donne 4,30:1. La barre reste donc à l'accent, et n'encode toujours pas le niveau
         de fiabilité (voir juste en dessous).

         bg-accent-text OU bg-neutral selon `muted`, jamais un 3e code couleur (2026-08-31,
         docs/design-v1.md §10.1/§10.2) : la barre ne distingue TOUJOURS PAS élevée de modérée
         (les deux restent bg-accent, comme au 2026-08-31 -- désigne le favori par sa position,
         jamais par sa couleur, déjà annoncé par la pastille de mention, GameCard.vue). `muted`
         n'ajoute pas un niveau : il retire l'accent en bloc pour "faible" (§10.2, "aucun accent,
         gris neutre"), exactement comme la note du favori dans GameCard.vue -- un binaire
         "accent ou pas", pas une 3e couleur. Régression du 2026-09-01 : bg-accent était resté
         inconditionnel après le retrait de barFill, annulant le refus de recommander de §10.2. -->
    <div
      class="absolute inset-y-0 left-1/2 w-1/2 origin-left rounded-r-full transition-transform duration-[600ms] ease-out motion-reduce:transition-none"
      :class="muted ? 'bg-neutral' : 'bg-accent-text'"
      :style="{ transform: `scaleX(${rightScale})` }"
      aria-hidden="true"
    />
    <div
      class="absolute inset-y-0 right-1/2 w-1/2 origin-right rounded-l-full transition-transform duration-[600ms] ease-out motion-reduce:transition-none"
      :class="muted ? 'bg-neutral' : 'bg-accent-text'"
      :style="{ transform: `scaleX(${leftScale})` }"
      aria-hidden="true"
    />
    <!-- PAS de repère central : supprimé le 2026-09-04, et à ne pas réintroduire.
         Le bord INTÉRIEUR de la barre est le repère. La barre part exactement du centre
         (`left-1/2` / `right-1/2`, `origin-left` / `origin-right`), donc la frontière
         piste→barre EST le centre -- et c'est la frontière la mieux contrastée de la
         jauge : 6,79:1 en sombre, 4,30:1 en clair. Le repère peint faisait doublon avec
         le bord qu'il devait signaler.

         Il était de surcroît impossible à rendre conforme. Démonstration, valable pour
         toute couleur et pas seulement pour celles essayées : un repère est à cheval sur
         la frontière, ses voisins sont donc la piste d'un côté et la barre de l'autre. En
         sombre, être à 3:1 d'une piste quasi noire (L = 0,005) exige une luminance
         >= 0,121 ; être à 3:1 d'une barre orange (L = 0,325) exige <= 0,075. Les deux
         intervalles sont DISJOINTS : aucune valeur ne satisfait les deux, balayage
         exhaustif des luminances à l'appui. Et ce n'est pas un accident de palette --
         **plus la barre se détache de sa piste, moins il reste de place pour une
         troisième couleur entre les deux**, les deux voisins occupant déjà les
         extrémités de l'échelle utilisable. Améliorer le contraste barre/piste (ce que
         fait le geste ci-dessus) ne pouvait donc que resserrer encore l'étau.

         La condition `muted ? 'bg-surface' : 'bg-text'` disparaît avec lui : ce repère
         conditionnel avait déjà coûté deux corrections (2026-08-31, 2026-09-01)
         précisément parce qu'il était coincé entre ces deux voisins. Voir §10.1. -->
  </div>
</template>
