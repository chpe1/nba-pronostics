<script setup>
import { ref, watch, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'

const emit = defineEmits(['imported'])

const fileInputRef = ref(null)
const selectedFile = ref(null)
const preview = ref(null)
const errorMessage = ref('')
const isLoading = ref(false)
const seasonType = ref('current')
const season = ref('')
const currentSeason = ref('')
const previousSeason = ref('')
const teams = ref([])
const teamId = ref('')

async function loadTeams() {
  try {
    teams.value = await apiFetch('/api/teams')
  } catch {
    // Non bloquant : seul le roster par équipe en a besoin, l'erreur backend
    // (team_id manquant) guide de toute façon si ce champ reste vide.
  }
}

async function loadCurrentSeason() {
  try {
    const settings = await apiFetch('/api/settings')
    currentSeason.value = settings.current_season
    previousSeason.value = settings.previous_season
    season.value = currentSeason.value
  } catch {
    // Non bloquant : le champ saison reste éditable manuellement si le
    // réglage n'a pas pu être chargé.
  }
}

// Pré-remplit le champ saison depuis le réglage admin (jamais vide par
// défaut) -- toujours éditable pour un cas exceptionnel.
watch(seasonType, (value) => {
  season.value = value === 'previous' ? previousSeason.value : currentSeason.value
})

function onFileChange(event) {
  selectedFile.value = event.target.files[0] ?? null
  preview.value = null
  errorMessage.value = ''
}

// Un <input type="file"> affiche le nom de fichier depuis son propre état
// DOM natif, pas depuis selectedFile -- il faut le réinitialiser
// explicitement via la ref, sinon le nom du fichier précédent reste affiché.
function resetFileInput() {
  selectedFile.value = null
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

async function upload(dryRun) {
  if (!selectedFile.value) return
  if (seasonType.value === 'previous' && !season.value.trim()) {
    errorMessage.value = "Précisez la saison précédente (ex: \"2024-2025\")."
    return
  }

  isLoading.value = true
  errorMessage.value = ''
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    const params = new URLSearchParams({ dry_run: dryRun, season_type: seasonType.value })
    // Toujours envoyé si renseigné : requis pour un calendrier de matchs
    // (indépendamment du sélecteur courant/précédent, sans objet pour ce
    // type de fichier), optionnel sinon.
    if (season.value.trim()) {
      params.set('season', season.value.trim())
    }
    // Requis uniquement pour un roster Advanced d'une seule équipe (fichier
    // sans colonne Team) ; sans effet sinon.
    if (teamId.value) {
      params.set('team_id', teamId.value)
    }
    const result = await apiFetch(`/api/imports/stats?${params.toString()}`, {
      method: 'POST',
      body: formData,
      isFormData: true,
    })

    if (dryRun) {
      preview.value = result
    } else {
      preview.value = null
      resetFileInput()
      emit('imported')
    }
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Échec de l'import."
    // Réinitialise aussi en cas de rejet d'une confirmation (pas d'un simple
    // aperçu) -- le fichier précédent n'a plus de raison de rester affiché.
    if (!dryRun) {
      resetFileInput()
    }
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  loadTeams()
  loadCurrentSeason()
})
</script>

<template>
  <div class="rounded-xl border border-border bg-surface p-4">
    <h2 class="mb-1 text-sm font-semibold text-text">Importer un fichier CSV Basketball-Reference</h2>
    <p class="mb-3 text-xs text-text-secondary">
      Classement (Expanded Standings), joueurs (Advanced — ligue entière ou roster d'une équipe),
      draft ou calendrier de la saison. Le type de fichier est <strong>détecté automatiquement</strong>
      à partir de ses colonnes — pas besoin de le préciser, dépose simplement le fichier tel quel.
    </p>

    <p class="mb-3 rounded-lg bg-surface-sunken px-3 py-2 text-xs text-text-secondary">
      Choisissez un fichier puis cliquez sur <strong>Aperçu</strong> — le type sera détecté
      automatiquement. Si tout est valide, cliquez sur <strong>Confirmer l'import</strong>.
    </p>

    <input
      ref="fileInputRef"
      type="file"
      accept=".csv"
      class="mb-3 block w-full text-sm text-text file:mr-3 file:cursor-pointer file:rounded-lg file:border-0 file:bg-text file:px-3 file:py-2 file:text-sm file:font-medium file:text-canvas hover:file:opacity-90"
      @change="onFileChange"
    />

    <fieldset class="mb-3 text-sm text-text">
      <legend class="mb-1 font-medium text-text">Saison (équipes / joueurs — sans objet pour la draft)</legend>
      <label class="mr-4 inline-flex items-center gap-1">
        <input v-model="seasonType" type="radio" value="current" />
        Saison courante<span v-if="currentSeason"> ({{ currentSeason }})</span>
      </label>
      <label class="inline-flex items-center gap-1">
        <input v-model="seasonType" type="radio" value="previous" />
        Saison précédente<span v-if="previousSeason"> ({{ previousSeason }})</span>
      </label>
      <input
        v-model="season"
        type="text"
        placeholder="ex: 2026-2027"
        class="mt-2 block w-40 rounded-lg border border-border px-2 py-1 text-sm"
      />
      <p class="mt-1 text-xs text-text-secondary">
        Pré-rempli depuis le réglage "Saison courante" (back-office Réglages), éditable si besoin.
        Requis pour un calendrier de matchs (le sélecteur ci-dessus est alors sans effet) ou pour "Saison précédente".
      </p>
    </fieldset>

    <fieldset class="mb-3 text-sm text-text">
      <legend class="mb-1 font-medium text-text">Équipe (roster par équipe uniquement)</legend>
      <select v-model="teamId" class="w-full max-w-xs rounded-lg border border-border px-2 py-1 text-sm">
        <option value="">—</option>
        <option v-for="team in teams" :key="team.id" :value="team.id">{{ team.name }}</option>
      </select>
      <p class="mt-1 text-xs text-text-secondary">
        Requis uniquement pour un roster Advanced d'une seule équipe (fichier sans colonne Team) ; sans effet sinon.
      </p>
    </fieldset>

    <div class="flex gap-2">
      <button
        type="button"
        class="rounded-lg border border-border px-3 py-2 text-sm font-medium disabled:opacity-50"
        :disabled="!selectedFile || isLoading"
        @click="upload(true)"
      >
        Aperçu
      </button>
      <button
        v-if="preview"
        type="button"
        class="rounded-lg bg-text px-3 py-2 text-sm font-medium text-canvas disabled:opacity-50"
        :disabled="isLoading"
        @click="upload(false)"
      >
        Confirmer l'import
      </button>
    </div>

    <p v-if="errorMessage" class="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">
      {{ errorMessage }}
    </p>

    <div v-if="preview" class="mt-4 text-sm">
      <p
        v-if="preview.resolved_team_name"
        class="mb-2 rounded-lg bg-surface-sunken px-3 py-2 font-medium text-text"
      >
        ⚠️ Équipe résolue pour cet import : <strong>{{ preview.resolved_team_name }} ({{ preview.resolved_team_abbreviation }})</strong>
        — vérifie que c'est la bonne avant de confirmer (le fichier ne contient aucune info d'équipe à croiser).
      </p>

      <p class="mb-2 text-text">
        Type détecté : <strong>{{ preview.import_type }}</strong>
        <span v-if="preview.season"> (saison {{ preview.season }})</span> —
        {{ preview.row_count }} ligne(s) valide(s), {{ preview.error_count }} erreur(s).
      </p>

      <div v-if="preview.errors.length" class="mb-2 rounded-lg bg-warning/10 px-3 py-2 text-warning">
        <p v-for="err in preview.errors" :key="err.row">Ligne {{ err.row }} : {{ err.message }}</p>
      </div>

      <div v-if="preview.sample_rows.length" class="overflow-x-auto">
        <table class="w-full border-collapse text-left text-xs">
          <thead>
            <tr>
              <th v-for="key in Object.keys(preview.sample_rows[0])" :key="key" class="border-b p-1 font-medium">
                {{ key }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in preview.sample_rows" :key="i">
              <td v-for="key in Object.keys(row)" :key="key" class="border-b p-1">{{ row[key] }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
