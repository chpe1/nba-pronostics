<script setup>
import { ref, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'

const selectedDate = ref(new Date().toISOString().slice(0, 10))
const games = ref([])
const forms = ref({})
const isLoading = ref(false)
const errorMessage = ref('')
const savingId = ref(null)
const savedId = ref(null)
const deletingId = ref(null)

function toLocalInputValue(isoString) {
  // game_date est une date/heure naïve (toujours US/ET, jamais convertie --
  // voir current_nba_date()) : on la découpe en composants bruts plutôt que
  // de passer par new Date(), qui appliquerait le fuseau du navigateur.
  const [datePart, timePart] = isoString.split('T')
  return `${datePart}T${(timePart || '00:00:00').slice(0, 5)}`
}

function buildForm(game) {
  return {
    game_date: toLocalInputValue(game.game_date),
    home_score: game.home_score,
    away_score: game.away_score,
    keep_auto_sync: !game.manually_overridden,
  }
}

async function loadGames() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    games.value = await apiFetch(`/api/games?date=${selectedDate.value}`)
    forms.value = Object.fromEntries(games.value.map((g) => [g.id, buildForm(g)]))
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les matchs.'
  } finally {
    isLoading.value = false
  }
}

async function save(game) {
  const form = forms.value[game.id]
  errorMessage.value = ''
  savedId.value = null
  savingId.value = game.id
  try {
    const payload = {
      game_date: form.game_date.length === 16 ? `${form.game_date}:00` : form.game_date,
      manually_overridden: !form.keep_auto_sync,
    }
    if (form.home_score !== null && form.home_score !== '') payload.home_score = Number(form.home_score)
    if (form.away_score !== null && form.away_score !== '') payload.away_score = Number(form.away_score)

    await apiFetch(`/api/games/${game.id}`, { method: 'PATCH', body: payload })
    // Recharge depuis le serveur plutôt qu'une simple mise à jour locale :
    // un changement de date peut faire sortir le match de la liste de la
    // date actuellement affichée (report vers un autre jour) -- un simple
    // patch en place laisserait le match affiché à tort sur l'ancienne date.
    savedId.value = game.id
    await loadGames()
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Échec de l'enregistrement."
  } finally {
    savingId.value = null
  }
}

async function deleteGame(game) {
  const confirmed = window.confirm(
    `Supprimer définitivement ${game.away_team_name} @ ${game.home_team_name} ? ` +
      'Le pronostic déjà calculé pour ce match (le cas échéant) sera aussi supprimé. Cette action est irréversible.'
  )
  if (!confirmed) return

  errorMessage.value = ''
  deletingId.value = game.id
  try {
    await apiFetch(`/api/games/${game.id}`, { method: 'DELETE' })
    games.value = games.value.filter((g) => g.id !== game.id)
    delete forms.value[game.id]
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Échec de la suppression.'
  } finally {
    deletingId.value = null
  }
}

onMounted(loadGames)
</script>

<template>
  <section class="mx-auto max-w-2xl space-y-4 px-4 py-6">
    <h1 class="text-xl font-semibold text-text">Correction manuelle des matchs</h1>
    <p class="text-sm text-text-secondary">
      Reporter la date d'un match ou corriger son score à la main (ex : indisponibilité de la
      synchronisation automatique).
    </p>

    <div class="flex items-center gap-2">
      <label for="date-picker" class="text-sm font-medium text-text">Date</label>
      <input
        id="date-picker"
        v-model="selectedDate"
        type="date"
        class="rounded-lg border border-border px-3 py-2 text-sm"
        @change="loadGames"
      />
    </div>

    <p v-if="errorMessage" class="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">{{ errorMessage }}</p>
    <p v-if="isLoading" class="text-sm text-text-secondary">Chargement…</p>
    <p v-else-if="games.length === 0" class="text-sm text-text-secondary">Aucun match ce jour-là.</p>

    <div v-for="game in games" :key="game.id" class="space-y-3 rounded-xl border border-border bg-surface p-4">
      <div class="text-sm font-medium text-text">
        {{ game.away_team_name }} @ {{ game.home_team_name }}
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div class="col-span-2">
          <label class="mb-1 block text-xs font-medium text-text">Date et heure (US/ET)</label>
          <input
            v-model="forms[game.id].game_date"
            type="datetime-local"
            class="w-full rounded-lg border border-border px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Score {{ game.away_team_abbreviation }} (ext.)</label>
          <input
            v-model="forms[game.id].away_score"
            type="number"
            class="w-full rounded-lg border border-border px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Score {{ game.home_team_abbreviation }} (dom.)</label>
          <input
            v-model="forms[game.id].home_score"
            type="number"
            class="w-full rounded-lg border border-border px-3 py-2 text-sm"
          />
        </div>
      </div>

      <label class="flex items-center gap-2 text-sm text-text">
        <input v-model="forms[game.id].keep_auto_sync" type="checkbox" class="rounded border-border" />
        Garder la synchronisation automatique active
      </label>
      <p class="text-xs text-text-secondary">
        Décochez uniquement si vous saisissez un score définitif à la main (ex : l'API de scores est
        indisponible) — un match reporté dont le score reste à venir doit garder cette case cochée.
      </p>

      <div class="flex gap-2">
        <button
          type="button"
          class="min-h-11 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
          :disabled="savingId === game.id || deletingId === game.id"
          @click="save(game)"
        >
          {{ savingId === game.id ? 'Enregistrement…' : 'Enregistrer' }}
        </button>
        <button
          type="button"
          class="min-h-11 rounded-lg border border-danger text-sm font-medium text-danger-text px-3 py-2 disabled:opacity-50"
          :disabled="savingId === game.id || deletingId === game.id"
          @click="deleteGame(game)"
        >
          {{ deletingId === game.id ? 'Suppression…' : 'Supprimer' }}
        </button>
      </div>
      <p v-if="savedId === game.id" class="text-xs text-success">Enregistré.</p>
    </div>
  </section>
</template>
