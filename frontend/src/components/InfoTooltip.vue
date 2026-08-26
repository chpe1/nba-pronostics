<script setup>
import { ref } from 'vue'

defineProps({
  text: { type: String, required: true },
})

// Clic/tap pour basculer (pas hover) : l'appli est mobile-first (CLAUDE.md),
// un survol serait inutilisable au doigt sur mobile -- et combiner hover et
// clic causait un bug réel (le clic rouvrait/refermait aussitôt ce que le
// hover venait d'ouvrir, sur desktop).
const isOpen = ref(false)
</script>

<template>
  <span class="relative inline-flex">
    <button
      type="button"
      class="ml-1 flex h-4 w-4 items-center justify-center rounded-full bg-gray-200 text-[10px] font-semibold leading-none text-gray-600 hover:bg-gray-300"
      :aria-label="text"
      @click="isOpen = !isOpen"
      @blur="isOpen = false"
    >
      i
    </button>
    <span
      v-if="isOpen"
      class="absolute bottom-full left-1/2 z-10 mb-1.5 w-56 -translate-x-1/2 rounded-lg bg-gray-900 p-2 text-xs font-normal leading-snug text-white shadow-lg"
    >
      {{ text }}
    </span>
  </span>
</template>
