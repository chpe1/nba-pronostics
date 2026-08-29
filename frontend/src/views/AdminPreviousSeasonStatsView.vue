<script setup>
import { ref, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'

const stats = ref([])
const forms = ref({})
const filterSeason = ref('')
const filterPlayerName = ref('')
const isLoading = ref(false)
const errorMessage = ref('')
const savingId = ref(null)
const savedId = ref(null)

const newStat = ref({ season: '', player_name: '', team_abbreviation: '', per: '', mpg: '' })
const isCreating = ref(false)
const createMessage = ref('')

function toNumberOrNull(value) {
  return value === '' || value === null || value === undefined ? null : Number(value)
}

function buildForm(stat) {
  return {
    season: stat.season,
    player_name: stat.player_name,
    team_abbreviation: stat.team_abbreviation,
    per: stat.per,
    mpg: stat.mpg,
  }
}

async function loadDefaultSeason() {
  try {
    const settings = await apiFetch('/api/settings')
    newStat.value.season = settings.previous_season
    filterSeason.value = settings.previous_season
  } catch {
    // Non bloquant : les champs saison restent éditables manuellement.
  }
}

async function loadStats() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const params = new URLSearchParams()
    if (filterSeason.value.trim()) params.set('season', filterSeason.value.trim())
    if (filterPlayerName.value.trim()) params.set('player_name', filterPlayerName.value.trim())
    stats.value = await apiFetch(`/api/previous-season-stats?${params.toString()}`)
    forms.value = Object.fromEntries(stats.value.map((s) => [s.id, buildForm(s)]))
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les statistiques.'
  } finally {
    isLoading.value = false
  }
}

async function save(stat) {
  const form = forms.value[stat.id]
  errorMessage.value = ''
  savedId.value = null
  savingId.value = stat.id
  try {
    const updated = await apiFetch(`/api/previous-season-stats/${stat.id}`, {
      method: 'PATCH',
      body: {
        season: form.season,
        player_name: form.player_name,
        team_abbreviation: form.team_abbreviation,
        per: toNumberOrNull(form.per),
        mpg: toNumberOrNull(form.mpg),
      },
    })
    const idx = stats.value.findIndex((s) => s.id === stat.id)
    stats.value[idx] = updated
    forms.value[stat.id] = buildForm(updated)
    savedId.value = stat.id
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Échec de l'enregistrement."
  } finally {
    savingId.value = null
  }
}

async function createStat() {
  errorMessage.value = ''
  createMessage.value = ''
  if (!newStat.value.season || !newStat.value.player_name || !newStat.value.team_abbreviation) {
    errorMessage.value = 'Saison, nom du joueur et abréviation d\'équipe sont obligatoires.'
    return
  }
  isCreating.value = true
  try {
    await apiFetch('/api/previous-season-stats', {
      method: 'POST',
      body: {
        season: newStat.value.season,
        player_name: newStat.value.player_name,
        team_abbreviation: newStat.value.team_abbreviation,
        per: toNumberOrNull(newStat.value.per),
        mpg: toNumberOrNull(newStat.value.mpg),
      },
    })
    createMessage.value = 'Ligne créée.'
    newStat.value = { ...newStat.value, player_name: '', team_abbreviation: '', per: '', mpg: '' }
    await loadStats()
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Échec de l'enregistrement."
  } finally {
    isCreating.value = false
  }
}

onMounted(async () => {
  await loadDefaultSeason()
  await loadStats()
})
</script>

<template>
  <section class="mx-auto max-w-2xl space-y-4 px-4 py-6">
    <h1 class="text-xl font-semibold text-gray-900">Statistiques joueurs (saison précédente)</h1>
    <p class="text-sm text-gray-500">
      Corriger une ligne à la main (ex : une résolution d'équipe erronée sur un cas d'encodage
      particulier) sans devoir réimporter tout le fichier ligue entière. Sert à la détection des
      transferts et au garde-fou petit échantillon — pas de suppression ici, seulement
      création/édition.
    </p>

    <p v-if="errorMessage" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{{ errorMessage }}</p>

    <div class="space-y-3 rounded-xl border border-gray-200 bg-white p-4">
      <h2 class="text-sm font-semibold text-gray-900">Ajouter une ligne</h2>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">Saison (ex : 2024-2025)</label>
          <input v-model="newStat.season" type="text" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">Équipe (abréviation)</label>
          <input v-model="newStat.team_abbreviation" type="text" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        <div class="col-span-2">
          <label class="mb-1 block text-xs font-medium text-gray-700">Nom complet du joueur</label>
          <input v-model="newStat.player_name" type="text" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">PER</label>
          <input v-model="newStat.per" type="number" step="0.1" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">MPG</label>
          <input v-model="newStat.mpg" type="number" step="0.1" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
      </div>
      <button
        type="button"
        class="w-full rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        :disabled="isCreating"
        @click="createStat"
      >
        {{ isCreating ? 'Enregistrement…' : 'Ajouter' }}
      </button>
      <p v-if="createMessage" class="text-xs text-emerald-700">{{ createMessage }}</p>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <label class="text-sm font-medium text-gray-700">Saison</label>
      <input
        v-model="filterSeason"
        type="text"
        placeholder="ex : 2024-2025"
        class="rounded-lg border border-gray-300 px-3 py-2 text-sm"
        @change="loadStats"
      />
      <label class="text-sm font-medium text-gray-700">Joueur</label>
      <input
        v-model="filterPlayerName"
        type="text"
        placeholder="rechercher un nom"
        class="rounded-lg border border-gray-300 px-3 py-2 text-sm"
        @change="loadStats"
      />
    </div>

    <p v-if="isLoading" class="text-sm text-gray-500">Chargement…</p>
    <p v-else-if="stats.length === 0" class="text-sm text-gray-500">Aucune ligne pour ces filtres.</p>

    <div v-for="stat in stats" :key="stat.id" class="space-y-3 rounded-xl border border-gray-200 bg-white p-4">
      <div class="grid grid-cols-2 gap-3">
        <div class="col-span-2">
          <label class="mb-1 block text-xs font-medium text-gray-700">Nom complet du joueur</label>
          <input v-model="forms[stat.id].player_name" type="text" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">Saison</label>
          <input v-model="forms[stat.id].season" type="text" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">Équipe (abréviation)</label>
          <input v-model="forms[stat.id].team_abbreviation" type="text" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">PER</label>
          <input v-model="forms[stat.id].per" type="number" step="0.1" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">MPG</label>
          <input v-model="forms[stat.id].mpg" type="number" step="0.1" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
      </div>

      <button
        type="button"
        class="w-full rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        :disabled="savingId === stat.id"
        @click="save(stat)"
      >
        {{ savingId === stat.id ? 'Enregistrement…' : 'Enregistrer' }}
      </button>
      <p v-if="savedId === stat.id" class="text-xs text-emerald-700">Enregistré.</p>
    </div>
  </section>
</template>
