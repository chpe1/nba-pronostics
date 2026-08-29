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

// Statut calendaire (home_calendar_status/away_calendar_status) : purement
// calendaire, jamais masqué même pour un match "À venir" -- le calendrier de
// la saison est connu à l'avance, contrairement au résultat du pronostic.
function calendarLabels(status) {
  if (!status) return []
  const labels = []
  if (status.is_back_to_back) labels.push('B2B')
  if (status.is_three_in_four) labels.push('3-en-4')
  return labels
}
const homeCalendarLabels = computed(() => calendarLabels(props.game.home_calendar_status))
const awayCalendarLabels = computed(() => calendarLabels(props.game.away_calendar_status))

// Absents/incertains : dans breakdown, donc déjà masqués en bloc avec le
// reste du résultat pour un match "À venir" (breakdown vaut null).
const homeAbsentPlayers = computed(() => prediction.value?.breakdown?.home?.absent_players ?? [])
const homeQuestionablePlayers = computed(() => prediction.value?.breakdown?.home?.questionable_players ?? [])
const awayAbsentPlayers = computed(() => prediction.value?.breakdown?.away?.absent_players ?? [])
const awayQuestionablePlayers = computed(() => prediction.value?.breakdown?.away?.questionable_players ?? [])
</script>

<template>
  <article class="rounded-xl border border-border bg-surface p-4 shadow-sm">
    <div class="mb-3 flex items-center justify-between text-sm text-text-secondary">
      <span>{{ gameTime }}</span>
      <ReliabilityGauge v-if="isRevealed" :reliability="prediction.reliability" />
      <span v-else-if="isUpcoming" class="rounded-full bg-surface-sunken px-2 py-1 text-xs font-medium text-text-secondary">
        À venir
      </span>
    </div>

    <div class="space-y-2">
      <div class="flex items-center justify-between" :class="{ 'font-semibold text-text': isAwayWinner }">
        <div>
          <div class="flex items-center gap-1">
            <span>{{ game.away_team_name }}</span>
            <span
              v-for="label in awayCalendarLabels"
              :key="label"
              class="rounded bg-warning/15 px-1.5 py-0.5 text-[10px] font-medium text-warning"
            >
              {{ label }}
            </span>
          </div>
          <div class="text-xs font-normal text-text-secondary">{{ formatRecord(game.away_team_recent_record) }}</div>
          <div v-if="isRevealed && awayAbsentPlayers.length" class="text-xs font-normal text-danger-text">
            Absents : {{ awayAbsentPlayers.map((p) => p.name).join(', ') }}
          </div>
          <div v-if="isRevealed && awayQuestionablePlayers.length" class="text-xs font-normal text-warning">
            Incertains : {{ awayQuestionablePlayers.map((p) => p.name).join(', ') }}
          </div>
        </div>
        <span v-if="isRevealed" class="tabular-nums">{{ prediction.away_team_note.toFixed(2) }}</span>
      </div>

      <div class="text-center text-xs text-text-disabled">@</div>

      <div class="flex items-center justify-between" :class="{ 'font-semibold text-text': isHomeWinner }">
        <div>
          <div class="flex items-center gap-1">
            <span>{{ game.home_team_name }}</span>
            <span
              v-for="label in homeCalendarLabels"
              :key="label"
              class="rounded bg-warning/15 px-1.5 py-0.5 text-[10px] font-medium text-warning"
            >
              {{ label }}
            </span>
          </div>
          <div class="text-xs font-normal text-text-secondary">{{ formatRecord(game.home_team_recent_record) }}</div>
          <div v-if="isRevealed && homeAbsentPlayers.length" class="text-xs font-normal text-danger-text">
            Absents : {{ homeAbsentPlayers.map((p) => p.name).join(', ') }}
          </div>
          <div v-if="isRevealed && homeQuestionablePlayers.length" class="text-xs font-normal text-warning">
            Incertains : {{ homeQuestionablePlayers.map((p) => p.name).join(', ') }}
          </div>
        </div>
        <span v-if="isRevealed" class="tabular-nums">{{ prediction.home_team_note.toFixed(2) }}</span>
      </div>
    </div>

    <div class="mt-3 border-t border-border pt-2 text-sm">
      <template v-if="isRevealed">
        <span class="text-text-secondary">Écart projeté :</span>
        <span class="font-medium text-text">{{ Math.abs(prediction.spread).toFixed(2) }}</span>
      </template>
      <span v-else-if="isUpcoming" class="text-text-disabled">
        Pronostic à venir — révélé quelques jours avant le match
      </span>
      <span v-else class="text-text-disabled">Pronostic pas encore calculé</span>
    </div>
  </article>
</template>
