<script setup>
import { computed } from 'vue'
import ReliabilityGauge from './ReliabilityGauge.vue'

const props = defineProps({
  game: {
    type: Object,
    required: true,
  },
})

const gameTime = computed(() =>
  new Date(props.game.game_date).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }),
)

const prediction = computed(() => props.game.prediction)

// Un pronostic déjà calculé mais trop anticipé (voir
// PREDICTION_REVEAL_THRESHOLD_DAYS, app/api/predictions.py) arrive avec
// is_upcoming=true et tous les champs de résultat à null -- distinct de
// "pas encore calculé" (prediction est alors entièrement null).
const isRevealed = computed(() => prediction.value && !prediction.value.is_upcoming)
const isUpcoming = computed(() => prediction.value && prediction.value.is_upcoming)

const isHomeWinner = computed(
  () => isRevealed.value && prediction.value.predicted_winner_team_id === props.game.home_team_id,
)
const isAwayWinner = computed(
  () => isRevealed.value && prediction.value.predicted_winner_team_id === props.game.away_team_id,
)

function formatRecord(record) {
  if (!record || record.games_considered === 0) {
    return 'Aucun match récent'
  }
  return `${record.wins}V-${record.losses}D sur les ${record.games_considered} derniers`
}
</script>

<template>
  <article class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
    <div class="mb-3 flex items-center justify-between text-sm text-gray-500">
      <span>{{ gameTime }}</span>
      <ReliabilityGauge v-if="isRevealed" :reliability="prediction.reliability" />
      <span v-else-if="isUpcoming" class="rounded-full bg-gray-100 px-2 py-1 text-xs font-medium text-gray-500">
        À venir
      </span>
    </div>

    <div class="space-y-2">
      <div class="flex items-center justify-between" :class="{ 'font-semibold text-gray-900': isAwayWinner }">
        <div>
          <div>{{ game.away_team_name }}</div>
          <div class="text-xs font-normal text-gray-500">{{ formatRecord(game.away_team_recent_record) }}</div>
        </div>
        <span v-if="isRevealed" class="tabular-nums">{{ prediction.away_team_note.toFixed(2) }}</span>
      </div>

      <div class="text-center text-xs text-gray-400">@</div>

      <div class="flex items-center justify-between" :class="{ 'font-semibold text-gray-900': isHomeWinner }">
        <div>
          <div>{{ game.home_team_name }}</div>
          <div class="text-xs font-normal text-gray-500">{{ formatRecord(game.home_team_recent_record) }}</div>
        </div>
        <span v-if="isRevealed" class="tabular-nums">{{ prediction.home_team_note.toFixed(2) }}</span>
      </div>
    </div>

    <div class="mt-3 border-t border-gray-100 pt-2 text-sm">
      <template v-if="isRevealed">
        <span class="text-gray-500">Écart projeté :</span>
        <span class="font-medium text-gray-900">{{ Math.abs(prediction.spread).toFixed(2) }}</span>
      </template>
      <span v-else-if="isUpcoming" class="text-gray-400">
        Pronostic à venir — révélé quelques jours avant le match
      </span>
      <span v-else class="text-gray-400">Pronostic pas encore calculé</span>
    </div>
  </article>
</template>
