<script setup>
import { computed } from 'vue'
import DivergentGauge from './DivergentGauge.vue'
import { reliabilityTreatment } from '@/constants/reliability'
import { calendarLabels } from '@/utils/pastilles'
import { teamRailColor } from '@/utils/teamColors'
import { useThemeStore } from '@/stores/theme'

const props = defineProps({
  game: {
    type: Object,
    required: true,
  },
  // Hauteur réservée à la zone de pastilles (0 à 3), calée par DashboardView.vue
  // sur le maximum RÉEL de la vue courante, pas sur le plafond théorique de 3
  // (docs/design-v1.md §10.3, correction du 2026-08-30 -- une carte isolée hors
  // Dashboard n'a pas cette information, d'où le défaut à 3, le plus prudent).
  reservedPastilleCount: {
    type: Number,
    default: 3,
  },
})

const gameTime = computed(() =>
  new Date(props.game.game_date).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }),
)

const prediction = computed(() => props.game.prediction)

// Filet de couleur d'équipe (docs/design-v1.md §5.7) : troisième axe,
// indépendant du mode clair/sombre et de l'accent -- calculé pour rester
// visible sur bg-surface dans le mode courant (teamRailColor lit
// useThemeStore, jamais data-theme lu directement ici). null pour toute
// équipe hors du périmètre des 6 de la base de développement -- pas de
// filet affiché dans ce cas (voir utils/teamColors.js).
const themeStore = useThemeStore()
const homeRailColor = computed(() => teamRailColor(props.game.home_team_abbreviation, themeStore.theme))
const awayRailColor = computed(() => teamRailColor(props.game.away_team_abbreviation, themeStore.theme))

// Trois états distincts (docs/design-v1.md §10.3, découverts au diagnostic du
// Lot 2 -- le document confondait les deux premiers jusque-là) :
// - jamais calculé (prediction === null) : aucun recalcul n'a encore eu lieu.
// - calculé mais masqué (is_upcoming === true) : un pronostic existe, mais le
//   match est trop loin dans le futur pour être révélé (comportement du Lot 1,
//   inchangé).
// - révélé (is_upcoming === false) : état nominal, tout est affiché.
const isRevealed = computed(() => Boolean(prediction.value) && !prediction.value.is_upcoming)
const isUpcoming = computed(() => Boolean(prediction.value) && prediction.value.is_upcoming)
const isNeverCalculated = computed(() => !prediction.value)

// "Journée passée" (§10.3) : détecté via `status`, jamais via la seule
// présence d'un score (voir docstring GameWithPredictionRead côté backend --
// un match FINISHED sans score renseigné reste théoriquement possible).
const isPast = computed(() => props.game.status === 'finished')
const scoreLine = computed(() => {
  if (!isPast.value || props.game.home_score === null || props.game.away_score === null) return null
  return `${props.game.away_score}-${props.game.home_score}`
})

const isHomeWinner = computed(
  () => isRevealed.value && prediction.value.predicted_winner_team_id === props.game.home_team_id,
)
const isAwayWinner = computed(
  () => isRevealed.value && prediction.value.predicted_winner_team_id === props.game.away_team_id,
)

const treatment = computed(() => (isRevealed.value ? reliabilityTreatment(prediction.value.reliability) : null))

// §10.2 : "faible" retire tout accent de la carte -- pas un 3e code couleur
// de la barre (elle n'en porte déjà aucun, voir DivergentGauge.vue), mais
// une ABSENCE d'accent partout où "forte"/"moyenne" en poseraient un (note
// du favori, jauge). Régression corrigée le 2026-09-01 : le retrait de
// barFill (jauge toujours bg-accent, décision distincte -- la barre ne doit
// jamais coder élevée/modérée) avait par erreur aussi supprimé ce retrait
// pour "faible", qui n'est pas la même règle.
const showsAccent = computed(() => isRevealed.value && prediction.value.reliability !== 'faible')

// La ligne disparaît entièrement (retourne null, pas un texte creux) quand
// l'équipe n'a aucun match FINISHED dans la fenêtre -- c'est l'état permanent
// des 30 équipes tant que la saison n'a pas commencé (corrigé en recette,
// 2026-08-30, voir docs/design-v1.md §10.5). Distinct d'un bilan 0V-0D avec
// games_considered > 0 (rare mais réel), qui reste affiché tel quel -- même
// principe de distinction que is_upcoming (§10.3) : se fier à l'indicateur
// explicite (games_considered), jamais le déduire de wins/losses à zéro.
function formatRecord(record) {
  if (!record || record.games_considered === 0) return null
  return `${record.wins}V-${record.losses}D sur les ${record.games_considered} derniers`
}

// Hauteur réservée à la zone de pastilles -- 0 pastille possible sur toute la
// vue (ex. effectif pas encore importé nulle part) fait disparaître la zone
// entièrement, 1-2 réservent une ligne, 3 réservent deux lignes (le rendu peut
// alors replier sur deux lignes). Voir docs/design-v1.md §10.3.
const pastilleZoneClass = computed(() => (props.reservedPastilleCount >= 3 ? 'min-h-12' : 'min-h-6'))

// Pastilles de contexte (§10.4) : faits bruts, trois maximum par équipe.
// Priorité absent > incertain > calendaire (le plus sévère d'abord) si les
// trois catégories sont présentes en même temps -- le calendrier reste
// toujours candidat (jamais masqué), les deux premières seulement si révélé.
//
// Le plafond de trois ne doit jamais faire disparaître un fait sans le
// signaler (correction du 2026-08-30, voir docs/design-v1.md §10.4) : au-delà
// de trois faits, seuls les deux premiers (priorité ci-dessus) gardent leur
// pastille -- la troisième position devient une pastille de RESTE, neutre
// (jamais une couleur sémantique, ce n'en est pas une), qui annonce le volume
// masqué au lieu de le taire.
function buildPastilles(absentPlayers, questionablePlayers, calendarLabelsList) {
  const items = []
  for (const p of absentPlayers) {
    items.push({ key: `absent-${p.name}`, text: `${p.name} absent`, cls: 'bg-danger/15 text-danger-text' })
  }
  for (const p of questionablePlayers) {
    items.push({ key: `q-${p.name}`, text: `${p.name} incertain`, cls: 'bg-warning/15 text-warning' })
  }
  for (const label of calendarLabelsList) {
    items.push({ key: `cal-${label}`, text: label, cls: 'bg-warning/15 text-warning' })
  }
  if (items.length <= 3) return items

  const shown = items.slice(0, 2)
  const remaining = items.length - shown.length
  shown.push({
    key: 'more',
    text: `+${remaining}`,
    cls: 'bg-neutral/15 text-neutral',
    // "+3" seul ne dit rien hors contexte visuel à un lecteur d'écran.
    ariaLabel: `${remaining} information${remaining > 1 ? 's' : ''} supplémentaire${remaining > 1 ? 's' : ''} non affichée${remaining > 1 ? 's' : ''} ici`,
  })
  return shown
}

// Absents/incertains : dans breakdown, donc déjà masqués en bloc avec le
// reste du résultat pour un match non révélé (breakdown vaut null).
const homeAbsentPlayers = computed(() => prediction.value?.breakdown?.home?.absent_players ?? [])
const homeQuestionablePlayers = computed(() => prediction.value?.breakdown?.home?.questionable_players ?? [])
const awayAbsentPlayers = computed(() => prediction.value?.breakdown?.away?.absent_players ?? [])
const awayQuestionablePlayers = computed(() => prediction.value?.breakdown?.away?.questionable_players ?? [])

const homePastilles = computed(() =>
  buildPastilles(
    isRevealed.value ? homeAbsentPlayers.value : [],
    isRevealed.value ? homeQuestionablePlayers.value : [],
    calendarLabels(props.game.home_calendar_status),
  ),
)
const awayPastilles = computed(() =>
  buildPastilles(
    isRevealed.value ? awayAbsentPlayers.value : [],
    isRevealed.value ? awayQuestionablePlayers.value : [],
    calendarLabels(props.game.away_calendar_status),
  ),
)
</script>

<template>
  <article class="rounded-xl border border-border bg-surface p-4 shadow-sm">
    <div class="mb-3 flex items-center justify-between text-sm">
      <span v-if="scoreLine" class="font-mono tabular-nums text-text">{{ scoreLine }}</span>
      <span v-else class="text-text-secondary">{{ gameTime }}</span>
      <span
        v-if="isRevealed"
        class="rounded-full px-2.5 py-1 text-xs font-medium"
        :class="treatment.pillClass"
      >
        {{ treatment.mention }}
      </span>
      <span v-else-if="isUpcoming" class="rounded-full bg-surface-sunken px-2 py-1 text-xs font-medium text-text-secondary">
        À venir
      </span>
    </div>

    <div class="space-y-2">
      <div class="flex items-center justify-between">
        <div>
          <div class="flex items-stretch gap-1.5">
            <span
              v-if="awayRailColor"
              class="w-[3px] rounded-full"
              :style="{ backgroundColor: awayRailColor }"
              aria-hidden="true"
            />
            <div
              class="font-title"
              :class="isRevealed ? (isAwayWinner ? 'text-text' : 'text-text-secondary') : 'text-text'"
            >
              {{ game.away_team_abbreviation }}
            </div>
          </div>
          <div v-if="reservedPastilleCount > 0" class="mt-1 flex flex-wrap items-start gap-1" :class="pastilleZoneClass">
            <span
              v-for="p in awayPastilles"
              :key="p.key"
              class="rounded px-1.5 py-0.5 text-[10px] font-medium"
              :class="p.cls"
              :aria-label="p.ariaLabel"
            >
              {{ p.text }}
            </span>
          </div>
          <div v-if="formatRecord(game.away_team_recent_record)" class="text-xs font-normal text-text-secondary">
            {{ formatRecord(game.away_team_recent_record) }}
          </div>
        </div>
        <span v-if="isRevealed" class="font-mono tabular-nums" :class="showsAccent && isAwayWinner ? 'text-accent-text' : 'text-text-secondary'">
          {{ prediction.away_team_note.toFixed(2) }}
        </span>
      </div>

      <div class="text-center text-xs text-text-disabled">@</div>

      <div class="flex items-center justify-between">
        <div>
          <div class="flex items-stretch gap-1.5">
            <span
              v-if="homeRailColor"
              class="w-[3px] rounded-full"
              :style="{ backgroundColor: homeRailColor }"
              aria-hidden="true"
            />
            <div
              class="font-title"
              :class="isRevealed ? (isHomeWinner ? 'text-text' : 'text-text-secondary') : 'text-text'"
            >
              {{ game.home_team_abbreviation }}
            </div>
          </div>
          <div v-if="reservedPastilleCount > 0" class="mt-1 flex flex-wrap items-start gap-1" :class="pastilleZoneClass">
            <span
              v-for="p in homePastilles"
              :key="p.key"
              class="rounded px-1.5 py-0.5 text-[10px] font-medium"
              :class="p.cls"
              :aria-label="p.ariaLabel"
            >
              {{ p.text }}
            </span>
          </div>
          <div v-if="formatRecord(game.home_team_recent_record)" class="text-xs font-normal text-text-secondary">
            {{ formatRecord(game.home_team_recent_record) }}
          </div>
        </div>
        <span v-if="isRevealed" class="font-mono tabular-nums" :class="showsAccent && isHomeWinner ? 'text-accent-text' : 'text-text-secondary'">
          {{ prediction.home_team_note.toFixed(2) }}
        </span>
      </div>
    </div>

    <div v-if="isRevealed" class="my-3">
      <DivergentGauge
        :home-note="prediction.home_team_note"
        :away-note="prediction.away_team_note"
        :home-team-abbreviation="game.home_team_abbreviation"
        :away-team-abbreviation="game.away_team_abbreviation"
        :threshold-high="game.reliability_threshold_high"
        :muted="!showsAccent"
      />
    </div>

    <div class="mt-3 border-t border-border pt-2 text-sm">
      <template v-if="isRevealed">
        <span class="text-text-secondary">Écart projeté : </span>
        <span class="font-mono tabular-nums font-medium text-text">{{ Math.abs(prediction.spread).toFixed(2) }}</span>
      </template>
      <span v-else-if="isUpcoming" class="text-text-disabled">
        Pronostic à venir — révélé quelques jours avant le match
      </span>
      <!-- Marqueur court : la cause (effectif pas importé) est globale à la
           journée, pas propre à ce match -- le bandeau contextuel (§9.1) la
           porte déjà en entier, pas la peine de la répéter sur chaque carte
           (corrigé en recette, 2026-08-30 : 13 répétitions identiques sur une
           journée de 12 matchs). -->
      <span v-else class="text-text-disabled">Pronostic indisponible</span>
    </div>
  </article>
</template>
