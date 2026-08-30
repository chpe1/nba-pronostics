<script setup>
import { ref, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'

const teams = ref([])
const selectedTeamId = ref('')
const players = ref([])
const forms = ref({})
const isLoading = ref(false)
const errorMessage = ref('')
const savingId = ref(null)
const savedId = ref(null)
const deletingId = ref(null)

const newPlayer = ref({ name: '', team_id: '', draft_pick: '', per: '', mpg: '' })
const isCreating = ref(false)
const createMessage = ref('')

function toNumberOrNull(value) {
  return value === '' || value === null || value === undefined ? null : Number(value)
}

function buildForm(player) {
  return {
    name: player.name,
    team_id: player.team_id,
    draft_pick: player.draft_pick,
    per: player.per,
    mpg: player.mpg,
  }
}

async function loadTeams() {
  try {
    teams.value = await apiFetch('/api/teams')
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les équipes.'
  }
}

async function loadPlayers() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const path = selectedTeamId.value ? `/api/players?team_id=${selectedTeamId.value}` : '/api/players'
    players.value = await apiFetch(path)
    forms.value = Object.fromEntries(players.value.map((p) => [p.id, buildForm(p)]))
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les joueurs.'
  } finally {
    isLoading.value = false
  }
}

async function save(player) {
  const form = forms.value[player.id]
  errorMessage.value = ''
  savedId.value = null
  savingId.value = player.id
  try {
    const updated = await apiFetch(`/api/players/${player.id}`, {
      method: 'PATCH',
      body: {
        name: form.name,
        team_id: Number(form.team_id),
        draft_pick: toNumberOrNull(form.draft_pick),
        per: toNumberOrNull(form.per),
        mpg: toNumberOrNull(form.mpg),
      },
    })
    const idx = players.value.findIndex((p) => p.id === player.id)
    players.value[idx] = updated
    forms.value[player.id] = buildForm(updated)
    savedId.value = player.id
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Échec de l'enregistrement."
  } finally {
    savingId.value = null
  }
}

async function deletePlayer(player) {
  const confirmed = window.confirm(
    `Supprimer définitivement ${player.name} (${player.team_abbreviation}) ? Cette action est irréversible.`
  )
  if (!confirmed) return

  errorMessage.value = ''
  deletingId.value = player.id
  try {
    await apiFetch(`/api/players/${player.id}`, { method: 'DELETE' })
    players.value = players.value.filter((p) => p.id !== player.id)
    delete forms.value[player.id]
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Échec de la suppression.'
  } finally {
    deletingId.value = null
  }
}

async function createPlayer() {
  errorMessage.value = ''
  createMessage.value = ''
  if (!newPlayer.value.name || !newPlayer.value.team_id) {
    errorMessage.value = 'Nom et équipe sont obligatoires.'
    return
  }
  isCreating.value = true
  try {
    const created = await apiFetch('/api/players', {
      method: 'POST',
      body: {
        name: newPlayer.value.name,
        team_id: Number(newPlayer.value.team_id),
        draft_pick: toNumberOrNull(newPlayer.value.draft_pick),
        per: toNumberOrNull(newPlayer.value.per),
        mpg: toNumberOrNull(newPlayer.value.mpg),
      },
    })
    createMessage.value = 'Joueur enregistré.'
    newPlayer.value = { name: '', team_id: newPlayer.value.team_id, draft_pick: '', per: '', mpg: '' }
    if (!selectedTeamId.value || Number(selectedTeamId.value) === created.team_id) {
      await loadPlayers()
    }
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Échec de l'enregistrement."
  } finally {
    isCreating.value = false
  }
}

onMounted(async () => {
  await loadTeams()
  await loadPlayers()
})
</script>

<template>
  <section class="mx-auto max-w-2xl space-y-4 px-4 py-6">
    <h1 class="text-xl font-semibold text-accent-text">Joueurs</h1>
    <p class="text-sm text-text-secondary">
      Ajouter ou corriger un joueur à la main (rookie drafté, correction ponctuelle). Un
      PER/MPG saisi ici est un simple placeholder : le prochain import CSV Advanced du
      même joueur l'écrase normalement, sans protection particulière.
    </p>

    <p v-if="errorMessage" class="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">{{ errorMessage }}</p>

    <div class="space-y-3 rounded-xl border border-border bg-surface p-4">
      <h2 class="text-sm font-semibold text-text">Ajouter un joueur</h2>
      <div class="grid grid-cols-2 gap-3">
        <div class="col-span-2">
          <label class="mb-1 block text-xs font-medium text-text">Nom complet (ex : LeBron James)</label>
          <input v-model="newPlayer.name" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div class="col-span-2">
          <label class="mb-1 block text-xs font-medium text-text">Équipe</label>
          <select v-model="newPlayer.team_id" class="min-h-11 w-full rounded-lg border border-border px-3 py-2 text-sm">
            <option value="" disabled>Sélectionner une équipe</option>
            <option v-for="team in teams" :key="team.id" :value="team.id">{{ team.name }}</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Pick draft</label>
          <input v-model="newPlayer.draft_pick" type="number" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">PER</label>
          <input v-model="newPlayer.per" type="number" step="0.1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">MPG</label>
          <input v-model="newPlayer.mpg" type="number" step="0.1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
      </div>
      <button
        type="button"
        class="min-h-11 w-full rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
        :disabled="isCreating"
        @click="createPlayer"
      >
        {{ isCreating ? 'Enregistrement…' : 'Ajouter / mettre à jour' }}
      </button>
      <p v-if="createMessage" class="text-xs text-success">{{ createMessage }}</p>
    </div>

    <div class="flex items-center gap-2">
      <label for="team-filter" class="text-sm font-medium text-text">Équipe</label>
      <select
        id="team-filter"
        v-model="selectedTeamId"
        class="min-h-11 rounded-lg border border-border px-3 py-2 text-sm"
        @change="loadPlayers"
      >
        <option value="">Toutes les équipes</option>
        <option v-for="team in teams" :key="team.id" :value="team.id">{{ team.name }}</option>
      </select>
    </div>

    <p v-if="isLoading" class="text-sm text-text-secondary">Chargement…</p>
    <p v-else-if="players.length === 0" class="text-sm text-text-secondary">Aucun joueur.</p>

    <div v-for="player in players" :key="player.id" class="space-y-3 rounded-xl border border-border bg-surface p-4">
      <div class="text-sm font-medium text-text">
        {{ player.team_abbreviation }} — {{ player.injury_status }}<span v-if="!player.is_active"> — inactif</span>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div class="col-span-2">
          <label class="mb-1 block text-xs font-medium text-text">Nom complet (ex : LeBron James)</label>
          <input v-model="forms[player.id].name" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div class="col-span-2">
          <label class="mb-1 block text-xs font-medium text-text">Équipe</label>
          <select v-model="forms[player.id].team_id" class="min-h-11 w-full rounded-lg border border-border px-3 py-2 text-sm">
            <option v-for="team in teams" :key="team.id" :value="team.id">{{ team.name }}</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Pick draft</label>
          <input v-model="forms[player.id].draft_pick" type="number" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">PER</label>
          <input v-model="forms[player.id].per" type="number" step="0.1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">MPG</label>
          <input v-model="forms[player.id].mpg" type="number" step="0.1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
      </div>

      <div class="flex gap-2">
        <button
          type="button"
          class="min-h-11 flex-1 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
          :disabled="savingId === player.id || deletingId === player.id"
          @click="save(player)"
        >
          {{ savingId === player.id ? 'Enregistrement…' : 'Enregistrer' }}
        </button>
        <button
          type="button"
          class="min-h-11 rounded-lg border border-danger text-sm font-medium text-danger-text px-3 py-2 disabled:opacity-50"
          :disabled="savingId === player.id || deletingId === player.id"
          @click="deletePlayer(player)"
        >
          {{ deletingId === player.id ? 'Suppression…' : 'Supprimer' }}
        </button>
      </div>
      <p v-if="savedId === player.id" class="text-xs text-success">Enregistré.</p>
    </div>
  </section>
</template>
