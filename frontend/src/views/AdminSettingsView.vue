<script setup>
import { ref, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'
import SettingsSlider from '@/components/SettingsSlider.vue'
import InfoTooltip from '@/components/InfoTooltip.vue'

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
    <h1 class="text-xl font-semibold text-gray-900">Réglages de l'algorithme</h1>

    <p v-if="errorMessage" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{{ errorMessage }}</p>
    <p v-if="successMessage" class="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
      {{ successMessage }}
    </p>

    <div v-if="settings" class="space-y-5 rounded-xl border border-gray-200 bg-white p-4">
      <div>
        <label class="mb-1 block text-sm font-medium text-gray-700">Saison courante</label>
        <input
          v-model="settings.current_season"
          type="text"
          placeholder="ex: 2026-2027"
          class="w-40 rounded-lg border border-gray-300 px-2 py-1 text-sm"
        />
        <p class="mt-1 text-xs text-gray-500">
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
        help="Transforme le pourcentage de victoires (0-1) en une note comparable aux autres composants de l'équation (PER, malus calendrier...) -- calibré pour une échelle 0-100 par défaut."
      />
      <SettingsSlider
        v-model="settings.per_impact_multiplier"
        label="Multiplicateur impact PER (Curseur B)"
        :min="0"
        :max="5"
        :step="0.05"
        help="Pondère le PER des joueurs absents (Out/Doubtful) avant de le soustraire à la note de base -- un PER brut (échelle ~10-30) écraserait sinon totalement une note calibrée sur 0-100."
      />
      <SettingsSlider
        v-model="settings.transfer_impact_multiplier"
        label="Multiplicateur Bonus/Malus Transferts"
        :min="0"
        :max="5"
        :step="0.05"
        help="Pondère le PER (saison précédente) des joueurs arrivés ou partis cet été avant de l'ajouter ou de le retrancher à la note -- même principe que le Curseur B, actif uniquement pendant les 10 premiers matchs de la saison de l'équipe."
      />
      <SettingsSlider
        v-model="settings.back_to_back_penalty"
        label="Malus Back-to-Back"
        :min="0"
        :max="20"
        :step="0.5"
        help="Points retirés à la note d'une équipe qui joue un match au lendemain immédiat d'un précédent, sans jour de repos."
      />
      <SettingsSlider
        v-model="settings.three_in_four_penalty"
        label="Malus 3 matchs en 4 nuits"
        :min="0"
        :max="20"
        :step="0.5"
        help="Points retirés à une équipe qui dispute son 3e match en 4 nuits (fatigue cumulée). Si le back-to-back s'applique aussi au même match, seul le malus le plus sévère des deux est appliqué, jamais les deux cumulés."
      />
      <SettingsSlider
        v-model="settings.mpg_threshold"
        label="Seuil MPG minimum"
        :min="0"
        :max="40"
        :step="1"
        help="Temps de jeu minimum (minutes/match) pour qu'un joueur absent ou incertain soit pris en compte dans le calcul -- écarte les joueurs de fin de banc dont l'absence n'a pas d'impact réel."
      />
      <SettingsSlider
        v-model="settings.player_sample_size_threshold"
        label="Seuil échantillon individuel (matchs)"
        :min="0"
        :max="15"
        :step="1"
        help="Sous ce nombre de matchs joués cette saison par un joueur, son PER/MPG de la saison précédente est utilisé à la place de sa valeur courante (trop peu fiable sur un si petit échantillon). Distinct du seuil équipe de 10 matchs (début de saison) : un joueur précis peut y rester après un retour de blessure même si son équipe l'a dépassé."
      />
      <SettingsSlider
        v-model="settings.reliability_threshold_low"
        label="Seuil de fiabilité — Moyenne"
        :min="0"
        :max="50"
        :step="0.5"
        help="Écart de points minimum (après tous les bonus/malus) pour que la jauge de fiabilité du pronostic passe de Faible à Moyenne."
      />
      <SettingsSlider
        v-model="settings.reliability_threshold_high"
        label="Seuil de fiabilité — Forte"
        :min="0"
        :max="50"
        :step="0.5"
        help="Écart de points minimum pour que la jauge de fiabilité passe de Moyenne à Forte."
      />

      <div>
        <label class="mb-1 flex items-center text-sm font-medium text-gray-700">
          Bonus Draft (JSON, pick → bonus)
          <InfoTooltip text="Bonus ajouté à la note d'une équipe pour chaque rookie drafté dans son effectif (selon son pick, ex: {&quot;1&quot;: 8, &quot;2&quot;: 6}). Actif seulement pendant les 10 premiers matchs de la saison de l'équipe." />
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
