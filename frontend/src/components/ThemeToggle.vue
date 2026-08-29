<script setup>
import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()
</script>

<template>
  <button
    type="button"
    class="flex h-11 w-11 items-center justify-center rounded-full border border-border bg-surface text-lg text-text transition-colors hover:bg-surface-sunken"
    :aria-label="themeStore.theme === 'dark' ? 'Passer en mode clair' : 'Passer en mode sombre'"
    :title="themeStore.theme === 'dark' ? 'Passer en mode clair' : 'Passer en mode sombre'"
    @click="themeStore.toggleTheme()"
  >
    <span aria-hidden="true">{{ themeStore.theme === 'dark' ? '☀️' : '🌙' }}</span>
  </button>
</template>
