<script setup>
import { ref } from 'vue'
import { apiFetchBlob, ApiError } from '@/services/apiClient'

const errorMessage = ref('')
const downloadingKey = ref(null)

const TEMPLATES = [
  { key: 'teams_home_away', label: 'Classement (Expanded Standings)' },
  { key: 'players_advanced_league', label: 'Joueurs Advanced — ligue entière' },
  { key: 'players_advanced_team', label: "Joueurs Advanced — roster d'une équipe" },
  { key: 'draft', label: 'Draft' },
  { key: 'schedule', label: 'Calendrier' },
  { key: 'roster', label: 'Effectif complet (NBA.com)' },
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
  <!-- Repliée par défaut : aide-mémoire consulté de temps en temps, il ne doit pas peser autant
       que le formulaire d'import juste en dessous. Même motif de <summary> que les sections du
       récapitulatif d'import (CsvUploadForm.vue). Le titre reste un <h2> dans le <summary>. -->
  <details class="rounded-xl border border-border bg-surface">
    <summary class="flex min-h-11 cursor-pointer items-center justify-between px-4 py-2">
      <h2 class="text-sm font-semibold text-text">Modèles de fichiers CSV</h2>
      <!-- Chevron décoratif : le <summary> porte déjà l'état ouvert/fermé pour les lecteurs
           d'écran. Pivote de 90° quand le <details> parent est ouvert. -->
      <svg
        aria-hidden="true"
        viewBox="0 0 20 20"
        class="h-4 w-4 shrink-0 text-text-secondary transition-transform motion-reduce:transition-none [details[open]_&]:rotate-90"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M7 4l6 6-6 6" />
      </svg>
    </summary>

    <div class="px-3 pb-3">
      <p class="mb-3 px-3 text-xs text-text-secondary">
        Aide-mémoire du format actuellement attendu par chaque type d'import — pas destiné à être
        rempli directement, juste pour voir vite ce qui a changé le jour où un format évolue.
      </p>

      <p v-if="errorMessage" class="mb-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">
        {{ errorMessage }}
      </p>

      <!-- Une ligne par modèle (flex-col, pas flex-wrap) : aucune colonne ne peut pousser les
           autres sur une rangée voisine. Liens de téléchargement (actions secondaires) : même
           largeur pour les six, jamais ajustée au libellé. -->
      <div class="flex flex-col gap-1">
        <button
          v-for="template in TEMPLATES"
          :key="template.key"
          type="button"
          class="flex min-h-11 w-full max-w-md items-center rounded-lg px-3 py-2 text-left text-xs font-medium text-accent-text underline underline-offset-2 hover:bg-surface-sunken disabled:opacity-50"
          :disabled="downloadingKey === template.key"
          @click="download(template.key)"
        >
          {{ downloadingKey === template.key ? 'Téléchargement…' : template.label }}
        </button>
      </div>

      <p class="mt-2 px-3 text-[11px] leading-snug text-text-secondary">
        Modèle simplifié : seules les colonnes obligatoires sont indiquées, votre vrai fichier en
        contiendra d'autres, aucun souci.
      </p>
    </div>
  </details>
</template>
