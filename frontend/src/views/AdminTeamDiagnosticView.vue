<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'
import MatchupResultCard from '@/components/MatchupResultCard.vue'
import InfoTooltip from '@/components/InfoTooltip.vue'
import { SETTINGS_HELP } from '@/constants/settingsHelp'

const teams = ref([])
const selectedTeamId = ref('')
const games = ref([])
const selectedGameId = ref(null)
const isLoadingGames = ref(false)
const errorMessage = ref('')
// Troisième état, distinct des deux autres : des données, une absence
// VÉRIFIÉE, un échec (docs/design-v1.md §12). Sans lui, un échec de
// chargement laissait à l'écran la liste du contexte précédent -- sous le
// nouveau contexte sélectionné, donc en affirmant qu'elle lui appartenait.
const loadFailed = ref(false)

const OVERRIDE_FIELDS = [
  { key: 'base_note_multiplier', label: 'Multiplicateur note de base (Curseur A)', help: SETTINGS_HELP.base_note_multiplier },
  { key: 'per_impact_multiplier', label: 'Multiplicateur impact PER (Curseur B)', help: SETTINGS_HELP.per_impact_multiplier },
  { key: 'transfer_impact_multiplier', label: 'Multiplicateur Bonus/Malus Transferts', help: SETTINGS_HELP.transfer_impact_multiplier },
  { key: 'back_to_back_penalty', label: 'Malus Back-to-Back', help: SETTINGS_HELP.back_to_back_penalty },
  { key: 'three_in_four_penalty', label: 'Malus 3 matchs en 4 nuits', help: SETTINGS_HELP.three_in_four_penalty },
  { key: 'mpg_threshold', label: 'Seuil MPG minimum', help: SETTINGS_HELP.mpg_threshold },
  { key: 'player_sample_size_threshold', label: 'Seuil échantillon individuel (matchs)', help: SETTINGS_HELP.player_sample_size_threshold },
  { key: 'reliability_threshold_low', label: 'Seuil de fiabilité — Moyenne', help: SETTINGS_HELP.reliability_threshold_low },
  { key: 'reliability_threshold_high', label: 'Seuil de fiabilité — Forte', help: SETTINGS_HELP.reliability_threshold_high },
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
  loadFailed.value = false
  if (!selectedTeamId.value) return

  isLoadingGames.value = true
  errorMessage.value = ''
  try {
    games.value = await apiFetch(`/api/predictions/by-team/${selectedTeamId.value}`)
  } catch (error) {
    // Seul écran des quatre qui vidait déjà `games` avant la requête -- mais
    // pour une autre raison (remettre à zéro la sélection de match au
    // changement d'équipe). Il n'affichait donc pas de données périmées, il
    // tombait directement dans le piège symétrique : son message « aucun
    // pronostic calculé pour cette équipe » s'affichait sur un échec, une
    // affirmation d'absence tout aussi fausse.
    loadFailed.value = true
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
    <h1 class="text-xl font-semibold text-text">Diagnostic équipes</h1>
    <p class="text-sm text-text-secondary">
      Décomposition détaillée des pronostics déjà calculés pour une équipe, et simulateur ponctuel
      pour tester d'autres réglages sans rien enregistrer.
    </p>

    <!-- Erreur qui ACCOMPAGNE des données encore valables (échec d'un
         enregistrement, d'une suppression) : elle se pose au-dessus. Un échec
         de CHARGEMENT, lui, prend la place de la liste, plus bas (§12). -->
    <p v-if="errorMessage && !loadFailed" class="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">{{ errorMessage }}</p>

    <div class="flex items-center gap-2">
      <label for="team-select" class="text-sm font-medium text-text">Équipe</label>
      <select
        id="team-select"
        v-model="selectedTeamId"
        class="min-h-11 rounded-lg border border-border px-3 py-2 text-sm"
        @change="loadGames"
      >
        <option value="" disabled>Sélectionner une équipe</option>
        <option v-for="team in teams" :key="team.id" :value="team.id">{{ team.name }}</option>
      </select>
    </div>

    <p v-if="isLoadingGames" class="text-sm text-text-secondary">Chargement…</p>
    <!-- L'échec prend la PLACE des données, il ne se superpose pas à elles
         (§12) : ni liste, ni message de vide. Placé avant la branche du vide
         dans la chaîne, il l'exclut mécaniquement -- les deux s'affichaient
         ensemble jusqu'ici, et l'une des deux était fausse. -->
    <div v-else-if="loadFailed" role="alert" class="rounded-lg bg-danger/10 p-3">
      <p class="text-sm text-danger-text">{{ errorMessage }}</p>
      <!-- Relance le contexte COURANT, sans rien changer à la sélection. -->
      <button
        type="button"
        class="mt-3 min-h-11 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
        :disabled="isLoadingGames"
        @click="loadGames"
      >
        Réessayer
      </button>
    </div>

    <p v-else-if="selectedTeamId && games.length === 0" class="text-sm text-text-secondary">
      Aucun pronostic calculé pour cette équipe pour l'instant (roster de la saison courante pas
      encore importé, ou aucun recalcul lancé).
    </p>

    <div v-if="games.length" class="space-y-2">
      <button
        v-for="game in games"
        :key="game.id"
        type="button"
        class="block min-h-11 w-full rounded-lg border px-3 py-2 text-left text-sm"
        :class="game.id === selectedGameId ? 'border-accent bg-accent-tint' : 'border-border bg-surface'"
        @click="selectGame(game)"
      >
        <span class="font-medium text-text">{{ formatDate(game.game_date) }}</span>
        — {{ game.away_team_abbreviation }} @ {{ game.home_team_abbreviation }}
        <span v-if="game.home_score !== null && game.away_score !== null" class="text-text-secondary">
          ({{ game.away_score }}-{{ game.home_score }})
        </span>
        <span class="text-text-disabled">— {{ game.status }}</span>
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

      <div class="space-y-3 rounded-xl border border-border bg-surface p-4">
        <h2 class="text-sm font-semibold text-text">Simuler avec d'autres réglages</h2>
        <p class="text-xs text-text-secondary">
          Champ vide = valeur réelle actuelle conservée. Rien n'est jamais enregistré (ni les
          réglages, ni un nouveau pronostic).
        </p>

        <div class="grid grid-cols-2 gap-3">
          <div v-for="field in OVERRIDE_FIELDS" :key="field.key">
            <label class="mb-1 flex items-center text-xs font-medium text-text">
              {{ field.label }}
              <InfoTooltip :text="field.help" />
            </label>
            <input
              v-model="overrideForm[field.key]"
              type="number"
              step="any"
              class="w-full rounded-lg border border-border px-2 py-1 text-sm"
            />
          </div>
        </div>

        <div>
          <label class="mb-1 flex items-center text-xs font-medium text-text">
            Bonus Draft (JSON, pick → bonus)
            <InfoTooltip :text="SETTINGS_HELP.draft_bonus_config" />
          </label>
          <textarea
            v-model="draftBonusOverrideText"
            rows="3"
            placeholder='ex: {"1": 8, "2": 6}'
            class="w-full rounded-lg border border-border p-2 font-mono text-xs"
          />
        </div>

        <p v-if="simulateError" class="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">{{ simulateError }}</p>

        <button
          type="button"
          class="min-h-11 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
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
