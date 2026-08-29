<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'

const teams = ref([])
const forms = ref({})
const searchText = ref('')
const isLoading = ref(false)
const errorMessage = ref('')
const savingId = ref(null)
const savedId = ref(null)

function buildForm(team) {
  return {
    name: team.name,
    abbreviation: team.abbreviation,
    conference: team.conference ?? '',
    division: team.division ?? '',
    current_streak: team.current_streak,
    win_pct_home: team.win_pct_home,
    win_pct_away: team.win_pct_away,
    win_pct_home_prev_season: team.win_pct_home_prev_season,
    win_pct_away_prev_season: team.win_pct_away_prev_season,
  }
}

async function loadTeams() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    teams.value = await apiFetch('/api/teams')
    forms.value = Object.fromEntries(teams.value.map((t) => [t.id, buildForm(t)]))
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les équipes.'
  } finally {
    isLoading.value = false
  }
}

const filteredTeams = computed(() => {
  const query = searchText.value.trim().toLowerCase()
  if (!query) return teams.value
  return teams.value.filter(
    (t) => t.name.toLowerCase().includes(query) || t.abbreviation.toLowerCase().includes(query)
  )
})

async function save(team) {
  const form = forms.value[team.id]
  errorMessage.value = ''
  savedId.value = null
  savingId.value = team.id
  try {
    const updated = await apiFetch(`/api/teams/${team.id}`, {
      method: 'PATCH',
      body: {
        name: form.name,
        abbreviation: form.abbreviation,
        conference: form.conference || null,
        division: form.division || null,
        current_streak: Number(form.current_streak),
        win_pct_home: Number(form.win_pct_home),
        win_pct_away: Number(form.win_pct_away),
        win_pct_home_prev_season: Number(form.win_pct_home_prev_season),
        win_pct_away_prev_season: Number(form.win_pct_away_prev_season),
      },
    })
    const idx = teams.value.findIndex((t) => t.id === team.id)
    teams.value[idx] = updated
    forms.value[team.id] = buildForm(updated)
    savedId.value = team.id
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Échec de l'enregistrement."
  } finally {
    savingId.value = null
  }
}

onMounted(loadTeams)
</script>

<template>
  <section class="mx-auto max-w-2xl space-y-4 px-4 py-6">
    <h1 class="text-xl font-semibold text-gray-900">Équipes</h1>
    <p class="text-sm text-gray-500">
      Corriger une équipe à la main (ex : win_pct erroné après un mauvais import). Un ajustement ici
      reste un simple placeholder : le prochain import CSV concerné l'écrase normalement, sans
      protection particulière — même comportement que pour les joueurs.
    </p>

    <p v-if="errorMessage" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{{ errorMessage }}</p>

    <input
      v-model="searchText"
      type="text"
      placeholder="Rechercher une équipe (nom ou abréviation)"
      class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
    />

    <p v-if="isLoading" class="text-sm text-gray-500">Chargement…</p>

    <div v-for="team in filteredTeams" :key="team.id" class="space-y-3 rounded-xl border border-gray-200 bg-white p-4">
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">Nom complet</label>
          <input v-model="forms[team.id].name" type="text" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">Abréviation</label>
          <input v-model="forms[team.id].abbreviation" type="text" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">% victoires domicile</label>
          <input v-model="forms[team.id].win_pct_home" type="number" step="0.001" min="0" max="1" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">% victoires extérieur</label>
          <input v-model="forms[team.id].win_pct_away" type="number" step="0.001" min="0" max="1" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">% victoires domicile (N-1)</label>
          <input v-model="forms[team.id].win_pct_home_prev_season" type="number" step="0.001" min="0" max="1" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">% victoires extérieur (N-1)</label>
          <input v-model="forms[team.id].win_pct_away_prev_season" type="number" step="0.001" min="0" max="1" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
      </div>

      <div class="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
        Les champs ci-dessous (conférence, division, série en cours) ne sont utilisés par aucun
        calcul de l'algorithme aujourd'hui — purement informatifs, les modifier n'influence aucun
        pronostic.
      </div>
      <div class="grid grid-cols-3 gap-3">
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">Conférence</label>
          <input v-model="forms[team.id].conference" type="text" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">Division</label>
          <input v-model="forms[team.id].division" type="text" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-gray-700">Série en cours</label>
          <input v-model="forms[team.id].current_streak" type="number" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
      </div>

      <button
        type="button"
        class="w-full rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        :disabled="savingId === team.id"
        @click="save(team)"
      >
        {{ savingId === team.id ? 'Enregistrement…' : 'Enregistrer' }}
      </button>
      <p v-if="savedId === team.id" class="text-xs text-emerald-700">Enregistré.</p>
    </div>
  </section>
</template>
