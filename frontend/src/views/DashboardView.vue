<script setup>
import { ref, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'
import { useAuthStore } from '@/stores/auth'
import GameCard from '@/components/GameCard.vue'

const authStore = useAuthStore()

// Valeur par défaut = date locale du navigateur, même convention que le
// sélecteur de date d'AdminGamesView.vue -- toujours transmise explicitement
// en paramètre plutôt que de compter sur le défaut serveur (current_nba_date()).
const selectedDate = ref(new Date().toISOString().slice(0, 10))
const games = ref([])
const isLoading = ref(true)
const isRecalculating = ref(false)
const errorMessage = ref('')

async function loadGames() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    games.value = await apiFetch(`/api/predictions/today?date=${selectedDate.value}`)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les matchs.'
  } finally {
    isLoading.value = false
  }
}

async function recalculate() {
  isRecalculating.value = true
  errorMessage.value = ''
  try {
    await apiFetch(`/api/predictions/recalculate?date=${selectedDate.value}`, { method: 'POST' })
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
      <h1 class="text-xl font-semibold text-text">Matchs</h1>
      <button
        v-if="authStore.isAuthenticated"
        type="button"
        class="rounded-lg bg-text px-3 py-2 text-sm font-medium text-canvas disabled:opacity-50"
        :disabled="isRecalculating"
        @click="recalculate"
      >
        {{ isRecalculating ? 'Recalcul en cours…' : 'Recalculer les pronostics de cette date' }}
      </button>
    </div>

    <div class="mb-4 flex items-center gap-2">
      <label for="dashboard-date-picker" class="text-sm font-medium text-text">Date</label>
      <input
        id="dashboard-date-picker"
        v-model="selectedDate"
        type="date"
        class="rounded-lg border border-border px-3 py-2 text-sm"
        @change="loadGames"
      />
    </div>

    <p v-if="errorMessage" class="mb-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">
      {{ errorMessage }}
    </p>

    <p v-if="isLoading" class="text-sm text-text-secondary">Chargement…</p>
    <p v-else-if="games.length === 0" class="text-sm text-text-secondary">Aucun match ce jour-là.</p>

    <div v-else class="space-y-3">
      <GameCard v-for="game in games" :key="game.id" :game="game" />
    </div>
  </section>
</template>
