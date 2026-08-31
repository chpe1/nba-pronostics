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
    <!-- Toujours bg-accent, quel que soit le niveau de fiabilité (retour en arrière assumé,
         2026-08-31, voir docs/design-v1.md §10.1) : la barre porte l'écart entre les deux notes et
         désigne le favori (par sa position, jamais par sa couleur -- les deux côtés ont toujours
         partagé la même couleur), pas le niveau de confiance -- déjà annoncé par la pastille de
         mention (GameCard.vue, RELIABILITY_TREATMENT.pillClass). Coder les deux sur la jauge
         doublait l'information sans jamais dire qui est favori par la couleur. -->
    <div
      class="absolute inset-y-0 left-1/2 w-1/2 origin-left rounded-r-full bg-accent transition-transform duration-[600ms] ease-out motion-reduce:transition-none"
      :style="{ transform: `scaleX(${rightScale})` }"
      aria-hidden="true"
    />
    <div
      class="absolute inset-y-0 right-1/2 w-1/2 origin-right rounded-l-full bg-accent transition-transform duration-[600ms] ease-out motion-reduce:transition-none"
      :style="{ transform: `scaleX(${leftScale})` }"
      aria-hidden="true"
    />
    <!-- Repère central : trois défauts cumulés, chacun mesuré en navigateur avant correction --
         un token à bon contraste sur le papier ne suffit pas si le pixel réel ne le porte jamais.
         1. Peint APRÈS les deux barres (pas avant) : le côté favori a TOUJOURS son bord intérieur
            exactement au centre par construction -- peint avant elle, le repère se faisait
            recouvrir pile à cet endroit, quelle que soit sa couleur.
         2. w-0.5 (2px), jamais w-px (1px) : à résolution d'écran normale (1x), une ligne de 1px
            positionnée via left:50% ne tombe quasiment jamais sur une frontière de pixel entière --
            elle se rend comme un flou d'anti-crénelage réparti sur deux pixels voisins, dont AUCUN
            n'affiche la vraie couleur du token (vérifié par lecture directe des pixels rendus :
            deux tons intermédiaires ternes, jamais rgb(156,163,175)). 2px laisse une chance réelle
            qu'au moins un pixel plein porte la couleur choisie.
         3. bg-text, jamais bg-text-secondary : --neutral (remplissage de la barre au niveau
            "faible") et --text-secondary sont la MÊME valeur hexacodée (#9CA3AF, vérifié dans
            style.css) -- un repère de cette couleur est invisible par définition sur ce
            remplissage précis, pas seulement mal contrasté. --text (quasi blanc/quasi noir selon
            le mode) reste distinct des trois remplissages possibles (accent/warning/neutral) ET du
            fond, dans les deux modes. -->
    <div class="absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 bg-text" aria-hidden="true" />
  </div>
</template>
