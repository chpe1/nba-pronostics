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
    <h1 class="text-xl font-semibold text-accent-text">Équipes</h1>
    <p class="text-sm text-text-secondary">
      Corriger une équipe à la main (ex : win_pct erroné après un mauvais import). Un ajustement ici
      reste un simple placeholder : le prochain import CSV concerné l'écrase normalement, sans
      protection particulière — même comportement que pour les joueurs.
    </p>

    <p v-if="errorMessage" class="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">{{ errorMessage }}</p>

    <input
      v-model="searchText"
      type="text"
      placeholder="Rechercher une équipe (nom ou abréviation)"
      class="w-full rounded-lg border border-border px-3 py-2 text-sm"
    />

    <p v-if="isLoading" class="text-sm text-text-secondary">Chargement…</p>

    <div v-for="team in filteredTeams" :key="team.id" class="space-y-3 rounded-xl border border-border bg-surface p-4">
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Nom complet</label>
          <input v-model="forms[team.id].name" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Abréviation</label>
          <input v-model="forms[team.id].abbreviation" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">% victoires domicile</label>
          <input v-model="forms[team.id].win_pct_home" type="number" step="0.001" min="0" max="1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">% victoires extérieur</label>
          <input v-model="forms[team.id].win_pct_away" type="number" step="0.001" min="0" max="1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">% victoires domicile (N-1)</label>
          <input v-model="forms[team.id].win_pct_home_prev_season" type="number" step="0.001" min="0" max="1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">% victoires extérieur (N-1)</label>
          <input v-model="forms[team.id].win_pct_away_prev_season" type="number" step="0.001" min="0" max="1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
      </div>

      <div class="rounded-lg bg-warning/10 px-3 py-2 text-xs text-warning">
        Les champs ci-dessous (conférence, division, série en cours) sont vides pour les 30
        équipes : aucun import ne les alimente, aucun calcul de l'algorithme ne les lit, et rien
        ne les affiche en dehors de ce formulaire. Les remplir n'a donc aucun effet visible
        aujourd'hui.
      </div>
      <div class="grid grid-cols-3 gap-3">
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Conférence</label>
          <input v-model="forms[team.id].conference" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Division</label>
          <input v-model="forms[team.id].division" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Série en cours</label>
          <input v-model="forms[team.id].current_streak" type="number" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
      </div>

      <button
        type="button"
        class="min-h-11 w-full rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
        :disabled="savingId === team.id"
        @click="save(team)"
      >
        {{ savingId === team.id ? 'Enregistrement…' : 'Enregistrer' }}
      </button>
      <p v-if="savedId === team.id" class="text-xs text-success">Enregistré.</p>
    </div>
  </section>
</template>
