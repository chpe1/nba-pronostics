<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
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

// Seuil d'apparition des cartes fantômes (§13). Mesuré le 2026-09-04 sur la
// base de développement, horloge réelle (jamais `clock.install`, §12) : la
// réponse de `/api/predictions/today` revient entre 6 et 58 ms (21 relevés,
// médiane 20 ms). Une date JAMAIS consultée n'est pas plus lente qu'une date
// déjà visitée -- médiane 17 ms contre 26 ms, l'écart tenant au nombre de
// matchs renvoyés et non à un quelconque cache. L'état de chargement complet
// durait 2 à 4 images d'affichage selon le clic (33 à 67 ms) : un facteur 2
// d'un clic à l'autre, sans aucun rapport avec la date -- c'est ce
// scintillement de durée variable qui se lisait comme « une fois sur deux ».
//
// 100 ms : au-dessus du maximum observé (67 ms) avec une marge de moitié,
// donc le cas local nominal ne déclenche plus rien ; c'est aussi la limite
// au-delà de laquelle une réaction cesse d'être perçue comme instantanée.
// En dessous du seuil, rien ne bouge : la nouvelle liste remplace l'ancienne
// directement.
const SKELETON_DELAY_MS = 100

// Durée minimale d'affichage une fois les fantômes montrés -- sans elle, on
// remplacerait un scintillement par un autre : une réponse arrivant à 105 ms
// les afficherait 5 ms, pire que jamais. 300 ms, c'est 18 images à 60 Hz
// contre les 2 à 4 mesurées aujourd'hui, et c'est la plus longue durée de
// mouvement du projet (`card-enter`, style.css) : en dessous, le bloc se
// lirait encore comme une transition, pas comme un état.
const SKELETON_MIN_VISIBLE_MS = 300

// État d'AFFICHAGE du chargement, distinct de `isLoading` (état de la
// requête) : les deux ne coïncident plus, c'est tout l'objet du seuil.
const showSkeleton = ref(false)

// Le message « Aucun match ce jour-là » ne doit jamais s'afficher avant
// qu'un chargement se soit réellement terminé : au tout premier montage,
// `games` est vide et les fantômes ne sont pas encore montrés (100 ms de
// délai) -- sans ce drapeau, l'écran affirmerait pendant ce laps de temps
// une absence de match qu'il n'a pas encore vérifiée.
const hasLoadedOnce = ref(false)

// Troisième état, distinct des deux autres : des données, une absence VÉRIFIÉE,
// un échec (§12). `hasLoadedOnce` distinguait déjà "pas encore vérifié" de
// "vérifié vide" ; il manquait "on a demandé, et on ne sait pas" -- sans quoi
// l'écran affirme quelque chose sur une date dont il n'a rien obtenu.
const loadFailed = ref(false)

let appearTimer = null
let hideTimer = null
let shownAt = 0

function armSkeleton() {
  clearTimeout(appearTimer)
  clearTimeout(hideTimer)
  hideTimer = null
  if (showSkeleton.value) return // déjà visible : on le laisse, sa durée minimale court toujours
  appearTimer = setTimeout(() => {
    appearTimer = null
    shownAt = performance.now()
    showSkeleton.value = true
  }, SKELETON_DELAY_MS)
}

function releaseSkeleton() {
  clearTimeout(appearTimer)
  appearTimer = null
  if (!showSkeleton.value) return
  const reste = SKELETON_MIN_VISIBLE_MS - (performance.now() - shownAt)
  if (reste <= 0) {
    showSkeleton.value = false
    return
  }
  hideTimer = setTimeout(() => {
    hideTimer = null
    showSkeleton.value = false
  }, reste)
}

onUnmounted(() => {
  clearTimeout(appearTimer)
  clearTimeout(hideTimer)
})

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
  armSkeleton()
  errorMessage.value = ''
  loadFailed.value = false
  try {
    games.value = await apiFetch(`/api/predictions/today?date=${selectedDate.value}`)
  } catch (error) {
    // La liste est vidée ICI, dans le `catch`, et surtout PAS au lancement de
    // la requête : ne pas la vider pendant le chargement est un choix
    // délibéré (les cartes fantômes s'y comptent pour que la page garde sa
    // hauteur, voir `skeletonCount`). Ce sont deux questions distinctes --
    // "qu'affiche-t-on pendant le chargement" a sa réponse depuis les
    // fantômes, "qu'affiche-t-on quand il échoue" n'en avait aucune, et la
    // liste précédente survivait par défaut. Elle s'affichait alors sous la
    // date nouvellement sélectionnée : l'écran affirmait que ces matchs
    // avaient lieu ce jour-là (constaté en recette le 2026-09-04, §12).
    games.value = []
    loadFailed.value = true
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les matchs.'
  } finally {
    isLoading.value = false
    hasLoadedOnce.value = true
    releaseSkeleton()
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
    <ContextBanner v-if="!showSkeleton" :games="games" />
    <!-- `bg-surface`, jamais `bg-surface-sunken` : ce bloc est posé
         directement sur le fond de page, or --surface-sunken vaut EXACTEMENT
         --canvas en mode sombre (#0E1015) -- mesuré invisible à la première
         tentative, exactement le piège déjà consigné en §5.2 (bug réel de
         CsvUploadForm.vue au Lot 3). Les blocs INTERNES peuvent, eux, rester
         en `bg-surface-sunken` : ils se détachent sur `bg-surface`, pas sur le
         fond de page.

         Hauteur DÉRIVÉE, plus jamais figée (corrigé le 2026-09-04) : ce bloc
         valait `h-[104px]` alors que le bandeau réel en mesurait 140,5 -- 36,5
         px d'écart, donc un saut de mise en page à l'arrivée des données,
         précisément ce qu'un squelette existe pour éviter. Il reprend
         désormais la structure de ContextBanner.vue (coiffe px-4 py-2, corps
         space-y-3 p-4, jauge compacte h-1) : la hauteur vient du même modèle
         de boîte et suivra toute évolution du bandeau, au lieu d'un nombre à
         resynchroniser à la main.

         La coiffe du squelette reste NEUTRE, jamais l'aplat d'accent : un
         bandeau vitrine n'existe que s'il y a un pronostic à montrer, et
         afficher sa coiffe colorée avant de le savoir affirmerait ce qui n'est
         pas encore vérifié (§13). -->
    <div
      v-else
      class="skeleton-pulse mb-4 overflow-hidden rounded-xl border border-border bg-surface"
      aria-hidden="true"
    >
      <div class="flex items-center justify-between px-4 py-2">
        <div class="h-4 w-32 rounded bg-surface-sunken" />
        <div class="h-5 w-28 rounded-full bg-surface-sunken" />
      </div>
      <div class="space-y-3 p-4">
        <div class="h-6 w-full rounded bg-surface-sunken" />
        <div class="h-1 w-full rounded-full bg-surface-sunken" />
        <div class="h-6 w-full rounded bg-surface-sunken" />
      </div>
    </div>

    <div v-if="authStore.isAuthenticated" class="mb-4">
      <button
        type="button"
        class="press-feedback min-h-11 rounded-lg bg-text px-3 py-2 text-sm font-medium text-canvas disabled:opacity-50"
        :disabled="isRecalculating"
        @click="recalculate"
      >
        {{ isRecalculating ? 'Recalcul en cours…' : 'Recalculer les pronostics de cette date' }}
      </button>
    </div>

    <!-- Erreur qui ACCOMPAGNE des données encore valables : uniquement l'échec
         d'un recalcul, dont les données à l'écran appartiennent bien à la date
         affichée. Un échec de CHARGEMENT, lui, ne se pose jamais au-dessus de
         la liste : il prend sa place, plus bas (§12). -->
    <p v-if="errorMessage && !loadFailed" class="mb-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">
      {{ errorMessage }}
    </p>

    <!-- Chargement : la grille garde sa forme (cartes fantômes) au lieu de
         laisser un écran vide. L'annonce accessible est portée par ce
         conteneur (`role="status"`), pas par les blocs eux-mêmes, qui sont
         `aria-hidden` -- un lecteur d'écran entend "Chargement des matchs…"
         une fois, jamais douze cartes vides. -->
    <div
      v-if="showSkeleton"
      role="status"
      aria-live="polite"
      aria-busy="true"
      class="grid grid-cols-1 gap-3 xl:grid-cols-3"
    >
      <span class="sr-only">Chargement des matchs…</span>
      <GameCardSkeleton v-for="n in skeletonCount" :key="`skeleton-${n}`" />
    </div>

    <!-- L'échec prend la PLACE des données, il ne se superpose pas à elles
         (§12) : ni cartes, ni bandeau, ni message de vide. Placé avant la
         branche « Aucun match » dans la chaîne, il l'exclut mécaniquement --
         les deux phrases s'affichaient ensemble jusqu'ici, et l'une des deux
         était fausse. -->
    <div v-else-if="loadFailed" role="alert" class="rounded-lg bg-danger/10 p-3">
      <p class="text-sm text-danger-text">{{ errorMessage }}</p>
      <!-- Relance la date COURANTE : une panne transitoire doit pouvoir se
           retenter sans re-cliquer la date, geste peu évident quand la date
           affichée est déjà la bonne. `loadGames` lit `selectedDate`, rien
           dans la sélection ne bouge. -->
      <button
        type="button"
        class="press-feedback mt-3 min-h-11 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
        :disabled="isLoading"
        @click="loadGames"
      >
        Réessayer
      </button>
    </div>

    <!-- Ne jamais affirmer une absence de match qui n'a pas été vérifiée :
         `hasLoadedOnce` couvre le tout premier montage (pendant les 100 ms de
         délai des fantômes), `!isLoading` couvre le cas révélé par le bouton
         ci-dessus -- après un échec la liste est vide, donc une nouvelle
         tentative afficherait « Aucun match ce jour-là » pendant les 100 ms
         qui précèdent l'apparition des fantômes. Une requête en cours n'a
         encore rien établi. -->
    <p v-else-if="hasLoadedOnce && !isLoading && games.length === 0" class="text-sm text-text-secondary">
      Aucun match ce jour-là.
    </p>

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
