<script setup>
import { computed } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  predictedWinnerTeamId: { type: Number, required: true },
  spread: { type: Number, required: true },
  reliability: { type: String, required: true },
  home: { type: Object, required: true },
  away: { type: Object, required: true },
})

const teams = computed(() => [props.home, props.away])

const winnerName = computed(() => {
  const winner = teams.value.find((t) => t.team_id === props.predictedWinnerTeamId)
  return winner ? winner.team_name : '?'
})

const reliabilityLabel = {
  faible: 'Faible',
  moyenne: 'Moyenne',
  forte: 'Forte',
}
</script>

<template>
  <div class="space-y-4 rounded-xl border border-gray-200 bg-white p-4">
    <h3 class="text-sm font-semibold text-gray-900">{{ title }}</h3>

    <div class="flex items-center justify-between rounded-lg bg-gray-50 p-3 text-sm">
      <div>
        <div class="font-medium text-gray-900">Vainqueur : {{ winnerName }}</div>
        <div class="text-gray-500">Écart : {{ spread.toFixed(1) }} pts</div>
      </div>
      <span class="rounded-full bg-gray-200 px-2 py-1 text-xs font-medium text-gray-700">
        Fiabilité {{ reliabilityLabel[reliability] || reliability }}
      </span>
    </div>

    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div v-for="team in teams" :key="team.team_id" class="space-y-2 text-sm">
        <div class="font-medium text-gray-900">
          {{ team.team_name }} <span class="text-xs text-gray-500">({{ team.is_home ? 'domicile' : 'extérieur' }})</span>
        </div>

        <dl class="space-y-1 text-xs text-gray-600">
          <div class="flex justify-between">
            <dt>Note de base<span v-if="team.in_early_season" class="ml-1 text-gray-400">(N-1, début de saison)</span></dt>
            <dd class="tabular-nums">{{ team.note_de_base.toFixed(3) }}</dd>
          </div>
          <div class="flex justify-between">
            <dt>Malus PER (absents)</dt>
            <dd class="tabular-nums">{{ team.injury_penalty.toFixed(1) }}</dd>
          </div>
          <ul v-if="team.absent_players.length" class="ml-2 list-disc space-y-0.5 pl-3 text-gray-500">
            <li v-for="p in team.absent_players" :key="p.name">
              {{ p.name }} — PER {{ p.per.toFixed(1) }}<span v-if="p.reason"> ({{ p.reason }})</span>
            </li>
          </ul>

          <div class="flex justify-between">
            <dt>
              Malus calendrier
              <span v-if="team.is_back_to_back" class="text-gray-400">(B2B)</span>
              <span v-else-if="team.is_three_in_four" class="text-gray-400">(3-en-4)</span>
            </dt>
            <dd class="tabular-nums">{{ team.calendar_penalty.toFixed(1) }}</dd>
          </div>
          <div class="flex justify-between">
            <dt>Bonus draft</dt>
            <dd class="tabular-nums">{{ team.draft_bonus.toFixed(1) }}</dd>
          </div>
          <div class="flex justify-between">
            <dt>Bonus/Malus transferts</dt>
            <dd class="tabular-nums">{{ team.transfer_adjustment.toFixed(1) }}</dd>
          </div>

          <ul v-if="team.questionable_players.length" class="space-y-0.5 text-amber-600">
            <li v-for="p in team.questionable_players" :key="p.name">
              Incertain : {{ p.name }} — PER {{ p.per.toFixed(1) }}<span v-if="p.reason"> ({{ p.reason }})</span>
            </li>
          </ul>

          <div class="flex justify-between border-t border-gray-200 pt-1 font-medium text-gray-900">
            <dt>Note finale</dt>
            <dd class="tabular-nums">{{ team.final_note.toFixed(1) }}</dd>
          </div>
        </dl>
      </div>
    </div>
  </div>
</template>
