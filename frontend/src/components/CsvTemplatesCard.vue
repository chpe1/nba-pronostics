<script setup>
import { ref } from 'vue'
import { apiFetchBlob, ApiError } from '@/services/apiClient'

const errorMessage = ref('')
const downloadingKey = ref(null)

const TEMPLATES = [
  { key: 'teams_home_away', label: 'Classement (Expanded Standings)' },
  { key: 'players_advanced_league', label: 'Joueurs Advanced — ligue entière' },
  {
    key: 'players_advanced_team',
    label: "Joueurs Advanced — roster d'une équipe",
    note: "Modèle simplifié : seules les colonnes obligatoires sont indiquées, votre vrai fichier en contiendra d'autres, aucun souci.",
  },
  { key: 'draft', label: 'Draft' },
  { key: 'schedule', label: 'Calendrier' },
]

async function download(key) {
  errorMessage.value = ''
  downloadingKey.value = key
  try {
    const blob = await apiFetchBlob(`/api/imports/template?type=${key}`)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `modele_${key}.csv`
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Échec du téléchargement.'
  } finally {
    downloadingKey.value = null
  }
}
</script>

<template>
  <div class="rounded-xl border border-border bg-surface p-4">
    <h2 class="mb-1 text-sm font-semibold text-text">Modèles de fichiers CSV</h2>
    <p class="mb-3 text-xs text-text-secondary">
      Aide-mémoire du format actuellement attendu par chaque type d'import — pas destiné à être
      rempli directement, juste pour voir vite ce qui a changé le jour où un format évolue.
    </p>

    <p v-if="errorMessage" class="mb-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">
      {{ errorMessage }}
    </p>

    <!-- max-w-[220px] posé sur le BOUTON, pas sur cette colonne (flex-col, align-items:stretch
         par défaut) : si le plafond était sur la colonne, la note héritait de la même largeur que
         le bouton quel que soit l'espace réellement disponible dans la rangée -- repéré en recette
         (note repliée sur ~1/3 de la carte sur grand écran, sans raison). En le posant sur le
         bouton seul, la colonne se redimensionne sur le plus large de ses deux enfants : les 4
         modèles sans note gardent le même rendu (bouton à 220px, rien d'autre à l'intérieur), et
         la note du 5e utilise la largeur qu'il lui faut, jusqu'à l'espace disponible. -->
    <div class="flex flex-wrap items-start gap-2">
      <div v-for="template in TEMPLATES" :key="template.key" class="flex flex-col gap-1">
        <button
          type="button"
          class="max-w-[220px] rounded-lg border border-border px-3 py-2 text-xs font-medium text-text disabled:opacity-50"
          :disabled="downloadingKey === template.key"
          @click="download(template.key)"
        >
          {{ downloadingKey === template.key ? 'Téléchargement…' : template.label }}
        </button>
        <p v-if="template.note" class="text-[11px] leading-snug text-text-secondary">{{ template.note }}</p>
      </div>
    </div>
  </div>
</template>
