<script setup>
import { ref, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'
import SettingsSlider from '@/components/SettingsSlider.vue'
import InfoTooltip from '@/components/InfoTooltip.vue'
import { SETTINGS_HELP } from '@/constants/settingsHelp'

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
        player_sample_size_threshold: settings.value.player_sample_size_threshold,
        reliability_threshold_low: settings.value.reliability_threshold_low,
        reliability_threshold_high: settings.value.reliability_threshold_high,
        transfer_impact_multiplier: settings.value.transfer_impact_multiplier,
        draft_bonus_config: draftBonusConfig,
        current_season: settings.value.current_season,
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
    <h1 class="text-xl font-semibold text-text">Réglages généraux de l'algorithme</h1>

    <p v-if="errorMessage" class="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">{{ errorMessage }}</p>
    <p v-if="successMessage" class="rounded-lg bg-success/10 px-3 py-2 text-sm text-success">
      {{ successMessage }}
    </p>

    <div v-if="settings" class="space-y-5 rounded-xl border border-border bg-surface p-4">
      <div>
        <label class="mb-1 block text-sm font-medium text-text">Saison courante</label>
        <input
          v-model="settings.current_season"
          type="text"
          placeholder="ex: 2026-2027"
          class="w-40 rounded-lg border border-border px-2 py-1 text-sm"
        />
        <p class="mt-1 text-xs text-text-secondary">
          À changer une fois par an, au début de la nouvelle saison (jamais déduit automatiquement
          d'une date). Pré-remplit le champ saison du formulaire d'import CSV.
        </p>
      </div>

      <SettingsSlider
        v-model="settings.base_note_multiplier"
        label="Multiplicateur note de base (Curseur A)"
        :min="0"
        :max="200"
        :step="5"
        :help="SETTINGS_HELP.base_note_multiplier"
      />
      <SettingsSlider
        v-model="settings.per_impact_multiplier"
        label="Multiplicateur impact PER (Curseur B)"
        :min="0"
        :max="5"
        :step="0.05"
        :help="SETTINGS_HELP.per_impact_multiplier"
      />
      <SettingsSlider
        v-model="settings.transfer_impact_multiplier"
        label="Multiplicateur Bonus/Malus Transferts"
        :min="0"
        :max="5"
        :step="0.05"
        :help="SETTINGS_HELP.transfer_impact_multiplier"
      />
      <SettingsSlider
        v-model="settings.back_to_back_penalty"
        label="Malus Back-to-Back"
        :min="0"
        :max="20"
        :step="0.5"
        :help="SETTINGS_HELP.back_to_back_penalty"
      />
      <SettingsSlider
        v-model="settings.three_in_four_penalty"
        label="Malus 3 matchs en 4 nuits"
        :min="0"
        :max="20"
        :step="0.5"
        :help="SETTINGS_HELP.three_in_four_penalty"
      />
      <SettingsSlider
        v-model="settings.mpg_threshold"
        label="Seuil MPG minimum"
        :min="0"
        :max="40"
        :step="1"
        :help="SETTINGS_HELP.mpg_threshold"
      />
      <SettingsSlider
        v-model="settings.player_sample_size_threshold"
        label="Seuil échantillon individuel (matchs)"
        :min="0"
        :max="15"
        :step="1"
        :help="SETTINGS_HELP.player_sample_size_threshold"
      />
      <SettingsSlider
        v-model="settings.reliability_threshold_low"
        label="Seuil de fiabilité — Moyenne"
        :min="0"
        :max="50"
        :step="0.5"
        :help="SETTINGS_HELP.reliability_threshold_low"
      />
      <SettingsSlider
        v-model="settings.reliability_threshold_high"
        label="Seuil de fiabilité — Forte"
        :min="0"
        :max="50"
        :step="0.5"
        :help="SETTINGS_HELP.reliability_threshold_high"
      />

      <div>
        <label class="mb-1 flex items-center text-sm font-medium text-text">
          Bonus Draft (JSON, pick → bonus)
          <InfoTooltip :text="SETTINGS_HELP.draft_bonus_config" />
        </label>
        <textarea
          v-model="draftBonusConfigText"
          rows="4"
          class="w-full rounded-lg border border-border p-2 font-mono text-xs"
        />
      </div>

      <button
        type="button"
        class="min-h-11 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
        :disabled="isSaving"
        @click="save"
      >
        {{ isSaving ? 'Enregistrement…' : 'Enregistrer' }}
      </button>
    </div>
  </section>
</template>
