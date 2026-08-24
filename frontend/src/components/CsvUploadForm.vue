<script setup>
import { ref } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'

const emit = defineEmits(['imported'])

const selectedFile = ref(null)
const preview = ref(null)
const errorMessage = ref('')
const isLoading = ref(false)
const seasonType = ref('current')
const season = ref('')

function onFileChange(event) {
  selectedFile.value = event.target.files[0] ?? null
  preview.value = null
  errorMessage.value = ''
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
    const result = await apiFetch(`/api/imports/stats?${params.toString()}`, {
      method: 'POST',
      body: formData,
      isFormData: true,
    })

    if (dryRun) {
      preview.value = result
    } else {
      preview.value = null
      selectedFile.value = null
      emit('imported')
    }
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Échec de l'import."
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="rounded-xl border border-gray-200 bg-white p-4">
    <h2 class="mb-3 text-sm font-semibold text-gray-900">Importer un fichier CSV Basketball-Reference</h2>

    <input
      type="file"
      accept=".csv"
      class="mb-3 block w-full text-sm text-gray-700"
      @change="onFileChange"
    />

    <fieldset class="mb-3 text-sm text-gray-700">
      <legend class="mb-1 font-medium text-gray-900">Saison (équipes / joueurs — sans objet pour la draft)</legend>
      <label class="mr-4 inline-flex items-center gap-1">
        <input v-model="seasonType" type="radio" value="current" />
        Saison courante
      </label>
      <label class="inline-flex items-center gap-1">
        <input v-model="seasonType" type="radio" value="previous" />
        Saison précédente
      </label>
      <input
        v-model="season"
        type="text"
        placeholder="ex: 2026-2027"
        class="mt-2 block w-40 rounded-lg border border-gray-300 px-2 py-1 text-sm"
      />
      <p class="mt-1 text-xs text-gray-500">
        Requis pour un calendrier de matchs (le sélecteur ci-dessus est alors sans effet) ou pour "Saison précédente" ; laissez vide sinon.
      </p>
    </fieldset>

    <div class="flex gap-2">
      <button
        type="button"
        class="rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium disabled:opacity-50"
        :disabled="!selectedFile || isLoading"
        @click="upload(true)"
      >
        Aperçu
      </button>
      <button
        v-if="preview"
        type="button"
        class="rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        :disabled="isLoading"
        @click="upload(false)"
      >
        Confirmer l'import
      </button>
    </div>

    <p v-if="errorMessage" class="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
      {{ errorMessage }}
    </p>

    <div v-if="preview" class="mt-4 text-sm">
      <p class="mb-2 text-gray-700">
        Type détecté : <strong>{{ preview.import_type }}</strong>
        <span v-if="preview.season"> (saison {{ preview.season }})</span> —
        {{ preview.row_count }} ligne(s) valide(s), {{ preview.error_count }} erreur(s).
      </p>

      <div v-if="preview.errors.length" class="mb-2 rounded-lg bg-amber-50 px-3 py-2 text-amber-800">
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
