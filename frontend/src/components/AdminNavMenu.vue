<script setup>
import { ref, onBeforeUnmount, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

// Ordre repris de docs/design-v1.md §11 (tableau des écrans du back-office).
const ADMIN_LINKS = [
  { name: 'admin-imports', label: 'Imports' },
  { name: 'admin-games', label: 'Matchs' },
  { name: 'admin-players', label: 'Joueurs' },
  { name: 'admin-teams', label: 'Équipes' },
  { name: 'admin-previous-season-stats', label: 'Stats N-1' },
  { name: 'admin-team-diagnostic', label: 'Diagnostic équipes' },
  { name: 'admin-database', label: 'Base de données' },
  { name: 'admin-settings', label: "Réglages généraux de l'algorithme" },
]

const isOpen = ref(false)
const menuRef = ref(null)
const triggerRef = ref(null)
const route = useRoute()

function onKeydown(event) {
  if (event.key === 'Escape') {
    close()
    triggerRef.value?.focus()
  }
}

function onClickOutside(event) {
  if (!menuRef.value?.contains(event.target) && !triggerRef.value?.contains(event.target)) {
    close()
  }
}

function open() {
  isOpen.value = true
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('click', onClickOutside)
}

function close() {
  if (!isOpen.value) return
  isOpen.value = false
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('click', onClickOutside)
}

function toggle() {
  if (isOpen.value) close()
  else open()
}

// Filet de sécurité : ferme aussi le menu si la navigation change pour une
// autre raison que le clic sur un lien ci-dessous (ex. bouton précédent).
watch(() => route.fullPath, close)

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('click', onClickOutside)
})
</script>

<template>
  <div class="relative">
    <button
      ref="triggerRef"
      type="button"
      class="flex h-11 items-center gap-1 rounded-lg px-3 text-sm font-medium text-text-secondary hover:bg-surface-sunken"
      aria-haspopup="menu"
      :aria-expanded="isOpen"
      @click="toggle"
    >
      Administration
      <span aria-hidden="true">{{ isOpen ? '▲' : '▼' }}</span>
    </button>
    <div
      v-if="isOpen"
      ref="menuRef"
      role="menu"
      class="absolute right-0 z-10 mt-1 w-64 overflow-hidden rounded-xl border border-border bg-surface py-1 shadow-lg"
    >
      <RouterLink
        v-for="link in ADMIN_LINKS"
        :key="link.name"
        :to="{ name: link.name }"
        role="menuitem"
        class="flex min-h-11 items-center px-4 py-2 text-sm text-text hover:bg-surface-sunken [&.router-link-exact-active]:text-accent-text"
        @click="close"
      >
        {{ link.label }}
      </RouterLink>
    </div>
  </div>
</template>
