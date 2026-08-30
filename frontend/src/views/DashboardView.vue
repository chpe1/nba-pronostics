<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'
import { useAuthStore } from '@/stores/auth'
import GameCard from '@/components/GameCard.vue'
import DateStrip from '@/components/DateStrip.vue'
import ContextBanner from '@/components/ContextBanner.vue'
import { maxRenderedPastilleCount } from '@/utils/pastilles'

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

// Hauteur des pastilles réservée sur la VUE courante, pas sur le plafond
// théorique de 3 (docs/design-v1.md §10.3) : tant que l'effectif de la saison
// courante n'est importé pour aucune équipe, ce maximum vaut 0 et la zone
// disparaît entièrement sur les 100+ prochains jours plutôt que de réserver
// un vide inutile sur chaque carte.
const reservedPastilleCount = computed(() => maxRenderedPastilleCount(games.value))

onMounted(loadGames)
</script>

<template>
  <section class="px-4 py-6">
    <h1 class="mb-4 text-xl font-semibold text-text">Matchs</h1>

    <DateStrip v-model="selectedDate" class="mb-4" @update:model-value="loadGames" />

    <ContextBanner v-if="!isLoading" :games="games" />

    <div v-if="authStore.isAuthenticated" class="mb-4">
      <button
        type="button"
        class="rounded-lg bg-text px-3 py-2 text-sm font-medium text-canvas disabled:opacity-50"
        :disabled="isRecalculating"
        @click="recalculate"
      >
        {{ isRecalculating ? 'Recalcul en cours…' : 'Recalculer les pronostics de cette date' }}
      </button>
    </div>

    <p v-if="errorMessage" class="mb-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">
      {{ errorMessage }}
    </p>

    <p v-if="isLoading" class="text-sm text-text-secondary">Chargement…</p>
    <p v-else-if="games.length === 0" class="text-sm text-text-secondary">Aucun match ce jour-là.</p>

    <!-- Grille ordinateur (§8.4) : 3 colonnes à partir de 1280 px (xl), seuil
         où la coquille elle-même s'élargit (Point 1) -- une seule colonne en
         dessous, aucun tri client (l'ordre vient de l'API tel quel). -->
    <div v-else class="grid grid-cols-1 gap-3 xl:grid-cols-3">
      <GameCard v-for="game in games" :key="game.id" :game="game" :reserved-pastille-count="reservedPastilleCount" />
    </div>
  </section>
</template>
