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

    <!-- Une ligne par modèle (flex-col, pas flex-wrap) -- pas un plafond de largeur sur la note
         (voir le commentaire retiré ci-dessous, conservé dans l'historique Git) : plafonner la
         note recréait juste un autre plafond arbitraire. Le vrai problème était le DÉCOUPAGE EN
         RANGÉES lui-même -- avec flex-wrap, une colonne notablement plus large que ses voisines
         (poussée par la largeur naturelle de la note) occupe presque toute sa rangée et repousse
         les colonnes suivantes (Draft, Calendrier) sur la ligne d'après, sans rapport avec le
         modèle qu'elles décrivent -- repéré en recette. En listant un modèle par ligne, aucune
         colonne ne peut plus jamais en pousser une autre : le bouton garde son plafond de 220px
         (max-w-[220px] sur le bouton, inchangé), la note reste libre de toute contrainte. -->
    <div class="flex flex-col items-start gap-2">
      <div v-for="template in TEMPLATES" :key="template.key" class="flex flex-col gap-1">
        <button
          type="button"
          class="min-h-11 max-w-[220px] rounded-lg border border-border px-3 py-2 text-xs font-medium text-text disabled:opacity-50"
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
