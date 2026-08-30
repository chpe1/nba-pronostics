<script setup>
import { computed } from 'vue'
import DivergentGauge from './DivergentGauge.vue'

// Bandeau contextuel (docs/design-v1.md §9). Quatre états dans le document,
// deux implémentés ici (vitrine / non révélé) -- passé (§9.3) réutilise le
// bandeau vitrine tel quel (pas de bilan calculable), en cours (§9.4) n'a pas
// d'état correspondant dans le modèle Game. Rien à afficher si la journée est
// vide : DashboardView.vue porte déjà son propre message dédié pour ce cas.
const props = defineProps({
  games: { type: Array, required: true },
})

const revealedGames = computed(() => props.games.filter((g) => g.prediction && !g.prediction.is_upcoming))

// Vitrine (§9.2/§9.3) : le match au plus grand écart, calculé côté client sur
// la liste déjà reçue (voir plan-design-lot2.md, diagnostic Point 0.6) --
// aucun appel supplémentaire.
const showcaseGame = computed(() => {
  if (!revealedGames.value.length) return null
  return revealedGames.value.reduce((best, g) =>
    Math.abs(g.prediction.spread) > Math.abs(best.prediction.spread) ? g : best,
  )
})

// Non révélé (§9.1) : deux raisons distinctes, mais un même traitement visuel
// neutre -- priorité au message "aucun pronostic calculé" dès qu'au moins un
// match de la journée en relève (§9.1, décision consignée). Corrigé le
// 2026-08-30 : le message initial ("effectif en cours de chargement")
// évoquait à tort une attente passagère, alors que c'est un état stable de
// plusieurs semaines (§12) -- aligné sur le texte, déjà juste, de la carte.
const hasNeverCalculated = computed(() => props.games.some((g) => !g.prediction))
const upcomingCount = computed(() => props.games.filter((g) => g.prediction?.is_upcoming).length)
</script>

<template>
  <div v-if="showcaseGame" class="mb-4 space-y-3 rounded-xl bg-accent-tint p-4 text-accent-on">
    <p class="text-xs font-medium">Pronostic du jour</p>
    <div class="flex items-center justify-between font-title">
      <span>{{ showcaseGame.away_team_abbreviation }}</span>
      <span class="font-mono tabular-nums">{{ showcaseGame.prediction.away_team_note.toFixed(2) }}</span>
    </div>
    <DivergentGauge
      compact
      :home-note="showcaseGame.prediction.home_team_note"
      :away-note="showcaseGame.prediction.away_team_note"
      :home-team-abbreviation="showcaseGame.home_team_abbreviation"
      :away-team-abbreviation="showcaseGame.away_team_abbreviation"
      :reliability="showcaseGame.prediction.reliability"
      :threshold-high="showcaseGame.reliability_threshold_high"
    />
    <div class="flex items-center justify-between font-title">
      <span>{{ showcaseGame.home_team_abbreviation }}</span>
      <span class="font-mono tabular-nums">{{ showcaseGame.prediction.home_team_note.toFixed(2) }}</span>
    </div>
  </div>

  <div v-else-if="games.length > 0" class="mb-4 rounded-xl bg-surface-sunken p-4 text-sm text-text-secondary">
    <template v-if="hasNeverCalculated">
      <p>Aucun pronostic calculé — l'effectif de la saison courante doit être importé, puis un
        recalcul lancé.</p>
      <!-- Secondaire, en retrait de la phrase ci-dessus : un complément
           d'information sur QUAND, pas une alerte. Distingue un état
           d'attente connue d'un état d'erreur, voir docs/design-v1.md §9.1. -->
      <p class="mt-1 text-xs text-text-disabled">
        Les rosters NBA ne se stabilisent qu'après les coupes d'effectif de présaison, mi-septembre
        — l'import ne sera possible qu'à partir de là.
      </p>
    </template>
    <p v-else>
      {{ upcomingCount }} match{{ upcomingCount > 1 ? 's' : '' }} programmé{{ upcomingCount > 1 ? 's' : '' }}
      — les pronostics seront révélés à l'approche de la date.
    </p>
  </div>
</template>
