<script setup>
import { ref, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'
import SettingsSlider from '@/components/SettingsSlider.vue'

const settings = ref(null)
const draftBonusConfigText = ref('{}')
const errorMessage = ref('')
const successMessage = ref('')
const isSaving = ref(false)

async function loadSettings() {
  errorMessage.value = ''
  try {
    settings.value = await apiFetch('/api/settings')
    draftBonusConfigText.value = JSON.stringify(settings.value.draft_bonus_config, null, 2)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les réglages.'
  }
}

async function save() {
  errorMessage.value = ''
  successMessage.value = ''

  let draftBonusConfig
  try {
    draftBonusConfig = JSON.parse(draftBonusConfigText.value)
  } catch {
    errorMessage.value = 'Le bonus draft doit être un JSON valide, ex: {"1": 5.0, "2": 3.0}.'
    return
  }

  isSaving.value = true
  try {
    settings.value = await apiFetch('/api/settings', {
      method: 'PUT',
      body: {
        base_note_multiplier: settings.value.base_note_multiplier,
        per_impact_multiplier: settings.value.per_impact_multiplier,
        back_to_back_penalty: settings.value.back_to_back_penalty,
        three_in_four_penalty: settings.value.three_in_four_penalty,
        mpg_threshold: settings.value.mpg_threshold,
        reliability_threshold_low: settings.value.reliability_threshold_low,
        reliability_threshold_high: settings.value.reliability_threshold_high,
        draft_bonus_config: draftBonusConfig,
      },
    })
    successMessage.value = 'Réglages enregistrés.'
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Échec de l\'enregistrement.'
  } finally {
    isSaving.value = false
  }
}

onMounted(loadSettings)
</script>

<template>
  <section class="mx-auto max-w-md space-y-4 px-4 py-6">
    <h1 class="text-xl font-semibold text-gray-900">Réglages de l'algorithme</h1>

    <p v-if="errorMessage" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{{ errorMessage }}</p>
    <p v-if="successMessage" class="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
      {{ successMessage }}
    </p>

    <div v-if="settings" class="space-y-5 rounded-xl border border-gray-200 bg-white p-4">
      <SettingsSlider v-model="settings.base_note_multiplier" label="Multiplicateur note de base (Curseur A)" :min="0" :max="5" :step="0.1" />
      <SettingsSlider v-model="settings.per_impact_multiplier" label="Multiplicateur impact PER (Curseur B)" :min="0" :max="5" :step="0.1" />
      <SettingsSlider v-model="settings.back_to_back_penalty" label="Malus Back-to-Back" :min="0" :max="20" :step="0.5" />
      <SettingsSlider v-model="settings.three_in_four_penalty" label="Malus 3 matchs en 4 nuits" :min="0" :max="20" :step="0.5" />
      <SettingsSlider v-model="settings.mpg_threshold" label="Seuil MPG minimum" :min="0" :max="40" :step="1" />
      <SettingsSlider v-model="settings.reliability_threshold_low" label="Seuil de fiabilité — Moyenne" :min="0" :max="30" :step="0.5" />
      <SettingsSlider v-model="settings.reliability_threshold_high" label="Seuil de fiabilité — Forte" :min="0" :max="30" :step="0.5" />

      <div>
        <label class="mb-1 block text-sm font-medium text-gray-700">
          Bonus Draft (JSON, pick → bonus)
        </label>
        <textarea
          v-model="draftBonusConfigText"
          rows="4"
          class="w-full rounded-lg border border-gray-300 p-2 font-mono text-xs"
        />
      </div>

      <button
        type="button"
        class="w-full rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        :disabled="isSaving"
        @click="save"
      >
        {{ isSaving ? 'Enregistrement…' : 'Enregistrer' }}
      </button>
    </div>
  </section>
</template>
