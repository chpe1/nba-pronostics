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
    <!-- bg-accent OU bg-neutral selon `muted`, jamais un 3e code couleur (2026-08-31,
         docs/design-v1.md §10.1/§10.2) : la barre ne distingue TOUJOURS PAS élevée de modérée
         (les deux restent bg-accent, comme au 2026-08-31 -- désigne le favori par sa position,
         jamais par sa couleur, déjà annoncé par la pastille de mention, GameCard.vue). `muted`
         n'ajoute pas un niveau : il retire l'accent en bloc pour "faible" (§10.2, "aucun accent,
         gris neutre"), exactement comme la note du favori dans GameCard.vue -- un binaire
         "accent ou pas", pas une 3e couleur. Régression du 2026-09-01 : bg-accent était resté
         inconditionnel après le retrait de barFill, annulant le refus de recommander de §10.2. -->
    <div
      class="absolute inset-y-0 left-1/2 w-1/2 origin-left rounded-r-full transition-transform duration-[600ms] ease-out motion-reduce:transition-none"
      :class="muted ? 'bg-neutral' : 'bg-accent'"
      :style="{ transform: `scaleX(${rightScale})` }"
      aria-hidden="true"
    />
    <div
      class="absolute inset-y-0 right-1/2 w-1/2 origin-right rounded-l-full transition-transform duration-[600ms] ease-out motion-reduce:transition-none"
      :class="muted ? 'bg-neutral' : 'bg-accent'"
      :style="{ transform: `scaleX(${leftScale})` }"
      aria-hidden="true"
    />
    <!-- Repère central : trois défauts cumulés initialement (2026-08-31), chacun mesuré en
         navigateur avant correction -- un token à bon contraste sur le papier ne suffit pas si le
         pixel réel ne le porte jamais.
         1. Peint APRÈS les deux barres (pas avant) : le côté favori a TOUJOURS son bord intérieur
            exactement au centre par construction -- peint avant elle, le repère se faisait
            recouvrir pile à cet endroit, quelle que soit sa couleur.
         2. w-0.5 (2px), jamais w-px (1px) : à résolution d'écran normale (1x), une ligne de 1px
            positionnée via left:50% ne tombe quasiment jamais sur une frontière de pixel entière --
            elle se rend comme un flou d'anti-crénelage réparti sur deux pixels voisins, dont AUCUN
            n'affiche la vraie couleur du token (vérifié par lecture directe des pixels rendus :
            deux tons intermédiaires ternes, jamais rgb(156,163,175)). 2px laisse une chance réelle
            qu'au moins un pixel plein porte la couleur choisie.
         3. bg-text, jamais bg-text-secondary : --neutral et --text-secondary sont la MÊME valeur
            hexacodée (#9CA3AF, vérifié dans style.css) -- un repère de cette couleur serait
            invisible par définition sur un remplissage neutre, pas seulement mal contrasté.

         4e défaut, distinct des trois premiers, trouvé le 2026-09-01 en réintroduisant `muted`
         (§10.2) : --text reste bien DIFFÉRENT de --neutral dans les deux modes (le piège nommé au
         point 3 ne se reproduit pas), mais leurs LUMINANCES sont trop proches pour satisfaire
         3:1 (WCAG 1.4.11) une fois le remplissage neutre réellement mesuré au pixel --
         2,33:1 en sombre, 2,66:1 en clair, sous le seuil dans les DEUX modes. "Différent" ne
         voulait pas dire "assez contrasté" -- une distinction que le point 3 n'avait pas eu à
         faire tant que le remplissage restait à l'accent (là, --text donne largement plus de 3:1
         dans les deux modes, vérifié). D'où un repère CONDITIONNEL comme les barres elles-mêmes :
         bg-text contre le remplissage à l'accent (inchangé, déjà mesuré conforme), bg-surface
         contre le remplissage neutre (mesuré 6,6:1 sombre / 6,8:1 clair) -- jamais une 3e couleur
         qui coderait un niveau, seulement celle qui reste lisible sur le fond réellement présent. -->
    <div
      class="absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2"
      :class="muted ? 'bg-surface' : 'bg-text'"
      aria-hidden="true"
    />
  </div>
</template>
