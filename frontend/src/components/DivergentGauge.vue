<script setup>
import { computed, onMounted, ref } from 'vue'
import { computeGaugeOffset } from '@/utils/gauge'
import { reliabilityTreatment } from '@/constants/reliability'

const props = defineProps({
  homeNote: { type: Number, required: true },
  awayNote: { type: Number, required: true },
  homeTeamAbbreviation: { type: String, required: true },
  awayTeamAbbreviation: { type: String, required: true },
  reliability: { type: String, required: true },
  thresholdHigh: { type: Number, required: true },
  // "Jauge réduite" du bandeau vitrine (§9.2) -- même mécanique, juste plus
  // fine, pas un second composant.
  compact: { type: Boolean, default: false },
})

// spread : positif = domicile favori (même convention que le backend, voir
// app/models/prediction.py) -- déport à droite pour le domicile, à gauche pour
// l'extérieur. Convention purement interne à ce composant, cohérente avec
// l'ordre extérieur (haut) / domicile (bas) déjà utilisé par GameCard.vue :
// lecture de haut en bas = lecture de gauche à droite.
const spread = computed(() => props.homeNote - props.awayNote)
const offset = computed(() => computeGaugeOffset(spread.value, props.thresholdHigh))
const treatment = computed(() => reliabilityTreatment(props.reliability))

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
    <!-- Repère central : bg-text-secondary, jamais bg-border -- mesuré et vérifié en navigateur
         (2026-08-31) que --border sur --surface-sunken donne ~1,3:1, très sous le seuil de 3:1
         requis pour un élément non textuel (WCAG 1.4.11), donc invisible en pratique malgré une
         géométrie de jauge par ailleurs correcte (offset/transform vérifiés justes séparément).
         --text-secondary y donne ~7,5:1 dans les deux modes. -->
    <div class="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-text-secondary" aria-hidden="true" />
    <div
      class="absolute inset-y-0 left-1/2 w-1/2 origin-left rounded-r-full transition-transform duration-[600ms] ease-out motion-reduce:transition-none"
      :class="treatment.barFill"
      :style="{ transform: `scaleX(${rightScale})` }"
      aria-hidden="true"
    />
    <div
      class="absolute inset-y-0 right-1/2 w-1/2 origin-right rounded-l-full transition-transform duration-[600ms] ease-out motion-reduce:transition-none"
      :class="treatment.barFill"
      :style="{ transform: `scaleX(${leftScale})` }"
      aria-hidden="true"
    />
  </div>
</template>
