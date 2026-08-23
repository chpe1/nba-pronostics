<script setup>
import { ref, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'
import { useAuthStore } from '@/stores/auth'
import GameCard from '@/components/GameCard.vue'

const authStore = useAuthStore()

const games = ref([])
const isLoading = ref(true)
const isRecalculating = ref(false)
const errorMessage = ref('')

async function loadGames() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    games.value = await apiFetch('/api/predictions/today')
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les matchs du jour.'
  } finally {
    isLoading.value = false
  }
}

async function recalculate() {
  isRecalculating.value = true
  errorMessage.value = ''
  try {
    await apiFetch('/api/predictions/recalculate', { method: 'POST' })
    await loadGames()
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Échec du recalcul des pronostics.'
  } finally {
    isRecalculating.value = false
  }
}

onMounted(loadGames)
</script>

<template>
  <section class="mx-auto max-w-2xl px-4 py-6">
    <div class="mb-4 flex items-center justify-between">
      <h1 class="text-xl font-semibold text-gray-900">Matchs du jour</h1>
      <button
        v-if="authStore.isAuthenticated"
        type="button"
        class="rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        :disabled="isRecalculating"
        @click="recalculate"
      >
        {{ isRecalculating ? 'Recalcul en cours…' : 'Recalculer les pronostics du jour' }}
      </button>
    </div>

    <p v-if="errorMessage" class="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
      {{ errorMessage }}
    </p>

    <p v-if="isLoading" class="text-sm text-gray-500">Chargement…</p>
    <p v-else-if="games.length === 0" class="text-sm text-gray-500">Aucun match aujourd'hui.</p>

    <div v-else class="space-y-3">
      <GameCard v-for="game in games" :key="game.id" :game="game" />
    </div>
  </section>
</template>
