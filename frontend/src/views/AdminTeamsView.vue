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
    win_pct_home: team.win_pct_home,
    win_pct_away: team.win_pct_away,
    win_pct_home_prev_season: team.win_pct_home_prev_season,
    win_pct_away_prev_season: team.win_pct_away_prev_season,
    point_diff_prev_season: team.point_diff_prev_season ?? '',
  }
}

// Case vide = inconnu : envoyé null, JAMAIS 0 (Number('') vaudrait 0 et fausserait la probabilité en silence).
function pointDiffPayload(value) {
  return value === '' || value === null || value === undefined ? null : Number(value)
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

// Garde-fou de saisie : sur une saison, la somme des écarts moyens des 30 équipes vaut 0 par construction
// (chaque match ajoute +marge à l'une, −marge à l'autre). Un écart notable une fois les 30 saisies signale
// une faute de frappe. Calculé sur les valeurs ENREGISTRÉES, pas sur les saisies en cours.
const pointDiffSummary = computed(() => {
  const known = teams.value.filter((t) => t.point_diff_prev_season !== null && t.point_diff_prev_season !== undefined)
  const sum = known.reduce((acc, t) => acc + t.point_diff_prev_season, 0)
  return { count: known.length, total: teams.value.length, sum }
})

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
        win_pct_home: Number(form.win_pct_home),
        win_pct_away: Number(form.win_pct_away),
        win_pct_home_prev_season: Number(form.win_pct_home_prev_season),
        win_pct_away_prev_season: Number(form.win_pct_away_prev_season),
        point_diff_prev_season: pointDiffPayload(form.point_diff_prev_season),
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
    <h1 class="text-xl font-semibold text-text">Équipes</h1>
    <p class="text-sm text-text-secondary">
      Corriger une équipe à la main (ex : win_pct erroné après un mauvais import). Un ajustement ici
      reste un simple placeholder : le prochain import CSV concerné l'écrase normalement, sans
      protection particulière — même comportement que pour les joueurs.
    </p>

    <p
      v-if="teams.length"
      data-testid="point-diff-summary"
      class="rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text"
    >
      Écart de points N-1 renseigné pour {{ pointDiffSummary.count }} équipe{{ pointDiffSummary.count > 1 ? 's' : '' }}
      sur {{ pointDiffSummary.total }} · somme :
      <span class="font-mono tabular-nums">{{ pointDiffSummary.sum.toFixed(2) }}</span>
      <span class="block text-xs text-text-secondary">
        Une fois les {{ pointDiffSummary.total }} renseignées, la somme doit valoir 0 à l'arrondi près ; un écart
        notable signale une faute de frappe. Une case vide n'est jamais 0 : la probabilité des matchs de cette
        équipe n'est alors pas calculée.
      </span>
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
        <div class="col-span-2">
          <label :for="`point-diff-${team.id}`" class="mb-1 block text-xs font-medium text-text">
            Écart de points moyen (N-1) — sert uniquement à la probabilité, jamais à la note
          </label>
          <input
            :id="`point-diff-${team.id}`"
            v-model="forms[team.id].point_diff_prev_season"
            type="number"
            step="0.01"
            min="-25"
            max="25"
            placeholder="vide = inconnu"
            class="w-full rounded-lg border border-border px-3 py-2 text-sm"
          />
        </div>
      </div>

      <button
        type="button"
        class="min-h-11 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
        :disabled="savingId === team.id"
        @click="save(team)"
      >
        {{ savingId === team.id ? 'Enregistrement…' : 'Enregistrer' }}
      </button>
      <p v-if="savedId === team.id" class="text-xs text-success">Enregistré.</p>
    </div>
  </section>
</template>
