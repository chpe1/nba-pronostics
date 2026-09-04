<script setup>
import { ref, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'

const stats = ref([])
const forms = ref({})
const filterSeason = ref('')
const filterPlayerName = ref('')
const isLoading = ref(false)
const errorMessage = ref('')
// Troisième état, distinct des deux autres : des données, une absence
// VÉRIFIÉE, un échec (docs/design-v1.md §12). Sans lui, un échec de
// chargement laissait à l'écran la liste du contexte précédent -- sous le
// nouveau contexte sélectionné, donc en affirmant qu'elle lui appartenait.
const loadFailed = ref(false)
const savingId = ref(null)
const savedId = ref(null)
const deletingId = ref(null)

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
  loadFailed.value = false
  try {
    const params = new URLSearchParams()
    if (filterSeason.value.trim()) params.set('season', filterSeason.value.trim())
    if (filterPlayerName.value.trim()) params.set('player_name', filterPlayerName.value.trim())
    stats.value = await apiFetch(`/api/previous-season-stats?${params.toString()}`)
    forms.value = Object.fromEntries(stats.value.map((s) => [s.id, buildForm(s)]))
  } catch (error) {
    // Vidée ICI : sans cela les lignes de la saison précédemment filtrée
    // restaient affichées sous les nouveaux filtres.
    stats.value = []
    forms.value = {}
    loadFailed.value = true
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

async function deleteStat(stat) {
  const confirmed = window.confirm(
    `Supprimer définitivement la ligne ${stat.player_name} (${stat.season}, ${stat.team_abbreviation}) ? ` +
      "N'affecte que les futurs recalculs (le joueur retombe sur le cas \"pas de fallback disponible\") -- " +
      'les pronostics déjà calculés ne changent pas. Cette action est irréversible.'
  )
  if (!confirmed) return

  errorMessage.value = ''
  deletingId.value = stat.id
  try {
    await apiFetch(`/api/previous-season-stats/${stat.id}`, { method: 'DELETE' })
    stats.value = stats.value.filter((s) => s.id !== stat.id)
    delete forms.value[stat.id]
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Échec de la suppression.'
  } finally {
    deletingId.value = null
  }
}

onMounted(async () => {
  await loadDefaultSeason()
  await loadStats()
})
</script>

<template>
  <section class="mx-auto max-w-2xl space-y-4 px-4 py-6">
    <h1 class="text-xl font-semibold text-text">Statistiques joueurs (saison précédente)</h1>
    <p class="text-sm text-text-secondary">
      Corriger une ligne à la main (ex : une résolution d'équipe erronée sur un cas d'encodage
      particulier) sans devoir réimporter tout le fichier ligue entière. Sert à la détection des
      transferts et au garde-fou petit échantillon.
    </p>

    <!-- Erreur qui ACCOMPAGNE des données encore valables (échec d'un
         enregistrement, d'une suppression) : elle se pose au-dessus. Un échec
         de CHARGEMENT, lui, prend la place de la liste, plus bas (§12). -->
    <p v-if="errorMessage && !loadFailed" class="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">{{ errorMessage }}</p>

    <div class="space-y-3 rounded-xl border border-border bg-surface p-4">
      <h2 class="text-sm font-semibold text-text">Ajouter une ligne</h2>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Saison (ex : 2024-2025)</label>
          <input v-model="newStat.season" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Équipe (abréviation)</label>
          <input v-model="newStat.team_abbreviation" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div class="col-span-2">
          <label class="mb-1 block text-xs font-medium text-text">Nom complet du joueur</label>
          <input v-model="newStat.player_name" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">PER</label>
          <input v-model="newStat.per" type="number" step="0.1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">MPG</label>
          <input v-model="newStat.mpg" type="number" step="0.1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
      </div>
      <button
        type="button"
        class="min-h-11 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
        :disabled="isCreating"
        @click="createStat"
      >
        {{ isCreating ? 'Enregistrement…' : 'Ajouter' }}
      </button>
      <p v-if="createMessage" class="text-xs text-success">{{ createMessage }}</p>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <label class="text-sm font-medium text-text">Saison</label>
      <input
        v-model="filterSeason"
        type="text"
        placeholder="ex : 2024-2025"
        class="rounded-lg border border-border px-3 py-2 text-sm"
        @change="loadStats"
      />
      <label class="text-sm font-medium text-text">Joueur</label>
      <input
        v-model="filterPlayerName"
        type="text"
        placeholder="rechercher un nom"
        class="rounded-lg border border-border px-3 py-2 text-sm"
        @change="loadStats"
      />
    </div>

    <p v-if="isLoading" class="text-sm text-text-secondary">Chargement…</p>
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
        :disabled="isLoading"
        @click="loadStats"
      >
        Réessayer
      </button>
    </div>

    <p v-else-if="stats.length === 0" class="text-sm text-text-secondary">Aucune ligne pour ces filtres.</p>

    <div v-for="stat in stats" :key="stat.id" class="space-y-3 rounded-xl border border-border bg-surface p-4">
      <div class="grid grid-cols-2 gap-3">
        <div class="col-span-2">
          <label class="mb-1 block text-xs font-medium text-text">Nom complet du joueur</label>
          <input v-model="forms[stat.id].player_name" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Saison</label>
          <input v-model="forms[stat.id].season" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Équipe (abréviation)</label>
          <input v-model="forms[stat.id].team_abbreviation" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">PER</label>
          <input v-model="forms[stat.id].per" type="number" step="0.1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">MPG</label>
          <input v-model="forms[stat.id].mpg" type="number" step="0.1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
      </div>

      <div class="flex gap-2">
        <button
          type="button"
          class="min-h-11 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
          :disabled="savingId === stat.id || deletingId === stat.id"
          @click="save(stat)"
        >
          {{ savingId === stat.id ? 'Enregistrement…' : 'Enregistrer' }}
        </button>
        <button
          type="button"
          class="min-h-11 rounded-lg border border-danger text-sm font-medium text-danger-text px-3 py-2 disabled:opacity-50"
          :disabled="savingId === stat.id || deletingId === stat.id"
          @click="deleteStat(stat)"
        >
          {{ deletingId === stat.id ? 'Suppression…' : 'Supprimer' }}
        </button>
      </div>
      <p v-if="savedId === stat.id" class="text-xs text-success">Enregistré.</p>
    </div>
  </section>
</template>
