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

// Largeur du panneau (w-64 ci-dessous, 16rem) -- dupliquée ici car nécessaire au calcul
// d'ancrage ; à resynchroniser si la classe change.
const MENU_WIDTH_PX = 256

const isOpen = ref(false)
const menuRef = ref(null)
const triggerRef = ref(null)
// Ancrage à droite par défaut (état normal, ≥475px -- voir docs/design-v1.md §15 pour le calcul
// de ce seuil). Recalculé une seule fois à l'ouverture, jamais en continu (voir onResize).
const anchorRight = ref(true)
const route = useRoute()

function fitsRight(triggerRect) {
  return triggerRect.right - MENU_WIDTH_PX >= 0
}
function fitsLeft(triggerRect) {
  return triggerRect.left + MENU_WIDTH_PX <= window.innerWidth
}

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

// Un menu ouvert pendant un redimensionnement/une rotation d'écran est dans un état douteux --
// l'ancrage calculé à l'ouverture ne correspond plus forcément à rien une fois la mise en page
// recalculée. On ferme plutôt que de recalculer en continu (même patron que le changement de
// route ci-dessous), et on rouvre correctement si besoin.
function onResize() {
  close()
}

function open() {
  isOpen.value = true
  // Bascule d'ancrage : teste les DEUX bords avant de choisir (jamais un seul -- un test à sens
  // unique finit par se faire prendre par le cas qu'il n'a jamais vérifié). Ancrage à droite
  // conservé par défaut (comportement actuel, déjà correct ≥475px) sauf s'il déborderait à gauche
  // ET que l'ancrage à gauche, lui, tiendrait. Si aucun des deux ne tient (fenêtre plus étroite
  // que le panneau lui-même), le choix ici n'a plus d'importance : `max-w-[calc(100vw-2rem)]` sur
  // le panneau (voir le template) rétrécit le panneau pour qu'il tienne quel que soit l'ancrage.
  const triggerRect = triggerRef.value?.getBoundingClientRect()
  anchorRight.value = !triggerRect || fitsRight(triggerRect) || !fitsLeft(triggerRect)
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('click', onClickOutside)
  window.addEventListener('resize', onResize)
}

function close() {
  if (!isOpen.value) return
  isOpen.value = false
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('click', onClickOutside)
  window.removeEventListener('resize', onResize)
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
  window.removeEventListener('resize', onResize)
})
</script>

<template>
  <div class="relative">
    <button
      ref="triggerRef"
      type="button"
      class="press-feedback flex h-11 items-center gap-1 rounded-lg px-3 text-sm font-medium text-text-secondary hover:bg-surface-sunken"
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
      class="menu-open absolute z-10 mt-1 w-64 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-border bg-surface py-1 shadow-lg"
      :class="anchorRight ? 'right-0' : 'left-0'"
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
