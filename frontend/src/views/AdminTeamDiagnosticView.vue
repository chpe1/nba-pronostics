<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'
import MatchupResultCard from '@/components/MatchupResultCard.vue'

const teams = ref([])
const selectedTeamId = ref('')
const games = ref([])
const selectedGameId = ref(null)
const isLoadingGames = ref(false)
const errorMessage = ref('')

const OVERRIDE_FIELDS = [
  { key: 'base_note_multiplier', label: 'Multiplicateur note de base (Curseur A)' },
  { key: 'per_impact_multiplier', label: 'Multiplicateur impact PER (Curseur B)' },
  { key: 'transfer_impact_multiplier', label: 'Multiplicateur Bonus/Malus Transferts' },
  { key: 'back_to_back_penalty', label: 'Malus Back-to-Back' },
  { key: 'three_in_four_penalty', label: 'Malus 3 matchs en 4 nuits' },
  { key: 'mpg_threshold', label: 'Seuil MPG minimum' },
  { key: 'player_sample_size_threshold', label: 'Seuil échantillon individuel (matchs)' },
  { key: 'reliability_threshold_low', label: 'Seuil de fiabilité — Moyenne' },
  { key: 'reliability_threshold_high', label: 'Seuil de fiabilité — Forte' },
]

const overrideForm = ref(Object.fromEntries(OVERRIDE_FIELDS.map((f) => [f.key, ''])))
const draftBonusOverrideText = ref('')
const simulationResult = ref(null)
const isSimulating = ref(false)
const simulateError = ref('')

const selectedGame = computed(() => games.value.find((g) => g.id === selectedGameId.value) || null)

async function loadTeams() {
  try {
    teams.value = await apiFetch('/api/teams')
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les équipes.'
  }
}

async function loadGames() {
  selectedGameId.value = null
  simulationResult.value = null
  games.value = []
  if (!selectedTeamId.value) return

  isLoadingGames.value = true
  errorMessage.value = ''
  try {
    games.value = await apiFetch(`/api/predictions/by-team/${selectedTeamId.value}`)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les matchs.'
  } finally {
    isLoadingGames.value = false
  }
}

function selectGame(game) {
  selectedGameId.value = game.id
  simulationResult.value = null
  simulateError.value = ''
}

function buildOverridesPayload() {
  const payload = {}
  for (const field of OVERRIDE_FIELDS) {
    const value = overrideForm.value[field.key]
    if (value !== '' && value !== null && value !== undefined) {
      payload[field.key] = Number(value)
    }
  }
  if (draftBonusOverrideText.value.trim() !== '') {
    payload.draft_bonus_config = JSON.parse(draftBonusOverrideText.value)
  }
  return payload
}

async function simulate() {
  if (!selectedGame.value) return
  simulateError.value = ''

  let overrides
  try {
    overrides = buildOverridesPayload()
  } catch {
    simulateError.value = 'Le bonus draft (JSON) est invalide.'
    return
  }

  isSimulating.value = true
  try {
    simulationResult.value = await apiFetch('/api/predictions/simulate', {
      method: 'POST',
      body: { game_id: selectedGame.value.id, overrides },
    })
  } catch (error) {
    simulateError.value = error instanceof ApiError ? error.message : 'Échec de la simulation.'
  } finally {
    isSimulating.value = false
  }
}

function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

onMounted(loadTeams)
</script>

<template>
  <section class="mx-auto max-w-3xl space-y-4 px-4 py-6">
    <h1 class="text-xl font-semibold text-gray-900">Diagnostic équipes</h1>
    <p class="text-sm text-gray-500">
      Décomposition détaillée des pronostics déjà calculés pour une équipe, et simulateur ponctuel
      pour tester d'autres réglages sans rien enregistrer.
    </p>

    <p v-if="errorMessage" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{{ errorMessage }}</p>

    <div class="flex items-center gap-2">
      <label for="team-select" class="text-sm font-medium text-gray-700">Équipe</label>
      <select
        id="team-select"
        v-model="selectedTeamId"
        class="rounded-lg border border-gray-300 px-3 py-2 text-sm"
        @change="loadGames"
      >
        <option value="" disabled>Sélectionner une équipe</option>
        <option v-for="team in teams" :key="team.id" :value="team.id">{{ team.name }}</option>
      </select>
    </div>

    <p v-if="isLoadingGames" class="text-sm text-gray-500">Chargement…</p>
    <p v-else-if="selectedTeamId && games.length === 0" class="text-sm text-gray-500">
      Aucun pronostic calculé pour cette équipe pour l'instant (roster de la saison courante pas
      encore importé, ou aucun recalcul lancé).
    </p>

    <div v-if="games.length" class="space-y-2">
      <button
        v-for="game in games"
        :key="game.id"
        type="button"
        class="block w-full rounded-lg border px-3 py-2 text-left text-sm"
        :class="game.id === selectedGameId ? 'border-gray-900 bg-gray-50' : 'border-gray-200 bg-white'"
        @click="selectGame(game)"
      >
        <span class="font-medium text-gray-900">{{ formatDate(game.game_date) }}</span>
        — {{ game.away_team_abbreviation }} @ {{ game.home_team_abbreviation }}
        <span v-if="game.home_score !== null && game.away_score !== null" class="text-gray-500">
          ({{ game.away_score }}-{{ game.home_score }})
        </span>
        <span class="text-gray-400">— {{ game.status }}</span>
      </button>
    </div>

    <template v-if="selectedGame">
      <MatchupResultCard
        title="Résultat réel"
        :predicted-winner-team-id="selectedGame.prediction.predicted_winner_team_id"
        :spread="selectedGame.prediction.spread"
        :reliability="selectedGame.prediction.reliability"
        :home="selectedGame.prediction.breakdown.home"
        :away="selectedGame.prediction.breakdown.away"
      />

      <div class="space-y-3 rounded-xl border border-gray-200 bg-white p-4">
        <h2 class="text-sm font-semibold text-gray-900">Simuler avec d'autres réglages</h2>
        <p class="text-xs text-gray-500">
          Champ vide = valeur réelle actuelle conservée. Rien n'est jamais enregistré (ni les
          réglages, ni un nouveau pronostic).
        </p>

        <div class="grid grid-cols-2 gap-3">
          <div v-for="field in OVERRIDE_FIELDS" :key="field.key">
            <label class="mb-1 block text-xs font-medium text-gray-700">{{ field.label }}</label>
            <input
              v-model="overrideForm[field.key]"
              type="number"
              step="any"
              class="w-full rounded-lg border border-gray-300 px-2 py-1 text-sm"
            />
          </div>
        </div>

        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">Bonus Draft (JSON, pick → bonus)</label>
          <textarea
            v-model="draftBonusOverrideText"
            rows="3"
            placeholder='ex: {"1": 8, "2": 6}'
            class="w-full rounded-lg border border-gray-300 p-2 font-mono text-xs"
          />
        </div>

        <p v-if="simulateError" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{{ simulateError }}</p>

        <button
          type="button"
          class="w-full rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          :disabled="isSimulating"
          @click="simulate"
        >
          {{ isSimulating ? 'Simulation…' : 'Simuler' }}
        </button>
      </div>

      <MatchupResultCard
        v-if="simulationResult"
        title="Résultat simulé"
        :predicted-winner-team-id="simulationResult.predicted_winner_team_id"
        :spread="simulationResult.spread"
        :reliability="simulationResult.reliability"
        :home="simulationResult.home"
        :away="simulationResult.away"
      />
    </template>
  </section>
</template>
