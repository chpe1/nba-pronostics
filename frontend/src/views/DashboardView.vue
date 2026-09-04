<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'
import { useAuthStore } from '@/stores/auth'
import GameCard from '@/components/GameCard.vue'
import GameCardSkeleton from '@/components/GameCardSkeleton.vue'
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

// Cascade d'entrée (§13) : UNE seule fois, jamais rejouée à chaque changement
// de date. Naviguer d'un jour à l'autre est l'usage principal du tableau de
// bord (DateStrip) -- relancer une vague de 12 cartes à chaque clic
// contredirait "le reste de l'interface est calme".
//
// Corrigé le 2026-09-04 après recette : le drapeau tombait au premier
// changement de date, ce qui rendait la cascade INOBSERVABLE dès que la
// première liste était vide -- cas nominal, la date du jour n'ayant
// généralement aucun match (vérifié : `?date=2026-09-04` renvoie `[]`). La
// vue se montait sur une liste vide, la cascade jouait sur zéro carte, et
// aucun clic ultérieur ne la rejouait.
//
// Règle retenue : le drapeau reste ARMÉ tant que la cascade n'a rien eu à
// animer, et ne tombe qu'à la première liste réellement peuplée -- que
// celle-ci arrive au montage ou dix clics plus tard. Pas de vague à CHAQUE
// changement de date (l'usage principal du tableau de bord), mais une
// cascade garantie sur la première liste qui a des cartes à montrer.
const playEntrance = ref(true)

async function loadGames() {
  // Désarmement au DÉBUT du chargement SUIVANT, jamais à la fin de celui qui
  // vient de peupler la liste. Première tentative (2026-09-04) : désarmer
  // juste après avoir affecté `games` -- la cascade ne jouait toujours pas,
  // mesuré `avec_cascade: 0`, parce que le drapeau retombait dans le même
  // tick, donc AVANT que Vue ne rende les cartes. Et le désarmer un tick plus
  // tard aurait retiré la classe en pleine animation.
  //
  // Ici, `games` porte encore la liste du chargement précédent : si elle
  // était peuplée, la cascade a déjà joué et on désarme ; si elle était vide,
  // le drapeau reste armé pour cette tentative-ci. Rien ne peut retirer la
  // classe pendant que l'animation tourne.
  if (playEntrance.value && games.value.length > 0) playEntrance.value = false

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

// Nombre de cartes fantômes pendant un chargement (§13) : celui de la journée
// précédemment affichée, pour que la page garde la hauteur qu'elle avait --
// `games` n'est vidé nulle part au lancement de la requête, il porte donc
// encore la liste précédente pendant tout le chargement. 3 par défaut au tout
// premier chargement, quand il n'y a aucune liste antérieure sur quoi se
// caler. Le nombre est une SUPPOSITION de gabarit, jamais une affirmation sur
// le contenu : c'est précisément pourquoi ce sont des blocs vides et non les
// cartes de la veille conservées à l'écran.
const skeletonCount = computed(() => games.value.length || 3)

onMounted(loadGames)
</script>

<template>
  <section class="px-4 py-6">
    <h1 class="mb-4 text-xl font-semibold text-text">Matchs</h1>

    <DateStrip v-model="selectedDate" class="mb-4" @update:model-value="loadGames" />

    <!-- Bandeau vitrine : remplacé par un bloc de même gabarit pendant le
         chargement, jamais escamoté -- sa disparition était la moitié de
         l'effondrement mesuré (§13). -->
    <ContextBanner v-if="!isLoading" :games="games" />
    <!-- `bg-surface`, jamais `bg-surface-sunken` : ce bloc est posé
         directement sur le fond de page, or --surface-sunken vaut EXACTEMENT
         --canvas en mode sombre (#0E1015) -- mesuré invisible à la première
         tentative, exactement le piège déjà consigné en §5.2 (bug réel de
         CsvUploadForm.vue au Lot 3). Les blocs INTERNES des cartes fantômes
         peuvent, eux, rester en `bg-surface-sunken` : ils se détachent sur
         `bg-surface`, pas sur le fond de page. -->
    <div
      v-else
      class="skeleton-pulse mb-4 h-[104px] rounded-xl border border-border bg-surface"
      aria-hidden="true"
    />

    <div v-if="authStore.isAuthenticated" class="mb-4">
      <button
        type="button"
        class="press-feedback rounded-lg bg-text px-3 py-2 text-sm font-medium text-canvas disabled:opacity-50"
        :disabled="isRecalculating"
        @click="recalculate"
      >
        {{ isRecalculating ? 'Recalcul en cours…' : 'Recalculer les pronostics de cette date' }}
      </button>
    </div>

    <p v-if="errorMessage" class="mb-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">
      {{ errorMessage }}
    </p>

    <!-- Chargement : la grille garde sa forme (cartes fantômes) au lieu de
         laisser un écran vide. L'annonce accessible est portée par ce
         conteneur (`role="status"`), pas par les blocs eux-mêmes, qui sont
         `aria-hidden` -- un lecteur d'écran entend "Chargement des matchs…"
         une fois, jamais douze cartes vides. -->
    <div
      v-if="isLoading"
      role="status"
      aria-live="polite"
      aria-busy="true"
      class="grid grid-cols-1 gap-3 xl:grid-cols-3"
    >
      <span class="sr-only">Chargement des matchs…</span>
      <GameCardSkeleton v-for="n in skeletonCount" :key="`skeleton-${n}`" />
    </div>

    <p v-else-if="games.length === 0" class="text-sm text-text-secondary">Aucun match ce jour-là.</p>

    <!-- Grille ordinateur (§8.4) : 3 colonnes à partir de 1280 px (xl), seuil
         où la coquille elle-même s'élargit (Point 1) -- une seule colonne en
         dessous, aucun tri client (l'ordre vient de l'API tel quel). -->
    <div v-else class="grid grid-cols-1 gap-3 xl:grid-cols-3">
      <!-- Décalage de 30ms par carte (§13), seule valeur qui varie d'une
           carte à l'autre -- posé en style inline plutôt qu'en classe : une
           classe par rang serait 12 classes générées pour rien. La classe
           `card-enter` (style.css) porte toute l'animation et sa
           neutralisation sous prefers-reduced-motion. -->
      <GameCard
        v-for="(game, index) in games"
        :key="game.id"
        :game="game"
        :reserved-pastille-count="reservedPastilleCount"
        :class="playEntrance ? 'card-enter' : null"
        :style="playEntrance ? { animationDelay: `${index * 30}ms` } : null"
      />
    </div>
  </section>
</template>
