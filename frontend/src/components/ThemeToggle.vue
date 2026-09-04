<script setup>
import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()
</script>

<template>
  <button
    type="button"
    class="press-feedback press-feedback-sm flex h-11 w-11 items-center justify-center rounded-full border border-border bg-surface text-accent-text hover:bg-surface-sunken"
    :aria-label="themeStore.theme === 'dark' ? 'Passer en mode clair' : 'Passer en mode sombre'"
    :title="themeStore.theme === 'dark' ? 'Passer en mode clair' : 'Passer en mode sombre'"
    @click="themeStore.toggleTheme()"
  >
    <!-- SVG en ligne, jamais un emoji (§12) : currentColor hérite de
         text-accent-text posé sur le bouton -- suit le mode ET l'axe
         d'accent automatiquement, sans logique JS. Formes réduites à
         l'essentiel (cercle + 4 rayons cardinaux / un croissant à un seul
         tracé) pour rester lisibles à 20px -- un soleil à douze rayons
         devient une tache à cette taille. -->
    <svg
      v-if="themeStore.theme === 'dark'"
      aria-hidden="true"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
    >
      <circle cx="12" cy="12" r="4.5" />
      <line x1="12" y1="1.5" x2="12" y2="4" />
      <line x1="12" y1="20" x2="12" y2="22.5" />
      <line x1="1.5" y1="12" x2="4" y2="12" />
      <line x1="20" y1="12" x2="22.5" y2="12" />
    </svg>
    <svg v-else aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  </button>
</template>
