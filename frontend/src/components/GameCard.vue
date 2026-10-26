<script setup>
import { computed } from 'vue'
import DivergentGauge from './DivergentGauge.vue'
import { reliabilityTreatment } from '@/constants/reliability'
import { calendarLabels } from '@/utils/pastilles'
import { resolveTeamBadges } from '@/utils/teamColors'
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

// Monogramme d'équipe (docs/design-v1.md §5.7/§10.3) : troisième axe,
// indépendant du mode clair/sombre et de l'accent -- remplace le filet de
// 3px écarté en recette (2026-09-02, trop fin et collé au tricode, lu comme
// une ponctuation plutôt qu'un signal d'identité). resolveTeamBadges lit
// useThemeStore (jamais data-theme lu directement ici) et résout les DEUX
// équipes ensemble : la couleur de l'extérieure dépend de celle du
// domicile (bascule sur sa secondaire en cas de collision perceptuelle,
// utils/teamColorCollision.js). null pour toute équipe hors du périmètre
// des 6 de la base de développement -- pas de badge affiché dans ce cas.
const themeStore = useThemeStore()
const badges = computed(() =>
  resolveTeamBadges(props.game.home_team_abbreviation, props.game.away_team_abbreviation, themeStore.theme),
)

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

// Début de saison : l'étiquette « forte » est plafonnée à « modérée » tant que la note de base d'au moins une équipe
// vient de la saison précédente (le serveur le dit dans breakdown.reliability_cap ; l'écart affiché, lui, ne change pas).
const reliabilityCapped = computed(
  () => isRevealed.value && prediction.value.breakdown?.reliability_cap?.capped === true,
)

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

// Probabilité de victoire (modèle d'écart de points), calculée À CÔTÉ de la note par le serveur
// (app/services/win_probability.py) : affichée dans son propre bloc, sans accent (l'accent reste à la note).
// Trois règles d'honnêteté : au-delà du seuil ci-dessous, elle n'est pas mesurée (et l'écran le dit) ; aucune
// comparaison aux cotes ni « value » ; elle ignore les absents (et l'écran le dit, avec leur nombre).
// Seuil comparé à la valeur ARRONDIE affichée : une probabilité affichée « 90 % » porte la mention, jamais
// un « 90 % » sans elle à côté d'un « 90 % » avec.
const UNMEASURED_FROM_PERCENT = 90

const probabilityInputs = computed(() => (isRevealed.value ? prediction.value.probability_inputs ?? null : null))
const homeProbability = computed(() => (isRevealed.value ? prediction.value.home_win_probability ?? null : null))
const hasProbability = computed(() => homeProbability.value !== null)
const homePercent = computed(() => Math.round(homeProbability.value * 100))
const awayPercent = computed(() => 100 - homePercent.value)
const isUnmeasuredLevel = computed(
  () => hasProbability.value && Math.max(homePercent.value, awayPercent.value) >= UNMEASURED_FROM_PERCENT,
)
// Écart N-1 non renseigné : le serveur n'a PAS calculé (jamais remplacé par 0) et dit pour quelle(s) équipe(s).
const missingPrevAbbreviations = computed(() => {
  const ids = probabilityInputs.value?.missing_prev_point_diff ?? []
  return ids.map((id) => (id === props.game.home_team_id ? props.game.home_team_abbreviation : props.game.away_team_abbreviation))
})
const gamesUsed = computed(() =>
  probabilityInputs.value
    ? { home: probabilityInputs.value.home.games_used, away: probabilityInputs.value.away.games_used }
    : null,
)
// Les absents de la carte sont ceux que la NOTE compte (au-dessus du seuil de minutes) ; la probabilité n'en
// compte aucun.
const absentCount = computed(() => homeAbsentPlayers.value.length + awayAbsentPlayers.value.length)

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
      <!-- Heure de New York (US/ET), affichée telle quelle : aucune conversion, voir limitation n°35. -->
      <span v-else class="text-text-secondary">
        {{ gameTime }}<span class="text-xs" data-testid="game-time-zone"> · New York</span>
      </span>
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
        <div class="flex items-center gap-2">
          <div
            v-if="badges.away"
            class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-xs font-title"
            :style="{ backgroundColor: badges.away.fill, color: badges.away.text }"
            aria-hidden="true"
          >
            {{ game.away_team_abbreviation }}
          </div>
          <div>
            <div
              class="font-title"
              :class="isRevealed ? (isAwayWinner ? 'text-text' : 'text-text-secondary') : 'text-text'"
            >
              {{ game.away_team_abbreviation }}
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
        </div>
        <span v-if="isRevealed" class="font-mono tabular-nums" :class="showsAccent && isAwayWinner ? 'text-accent-text' : 'text-text-secondary'">
          {{ prediction.away_team_note.toFixed(2) }}
        </span>
      </div>

      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <div
            v-if="badges.home"
            class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-xs font-title"
            :style="{ backgroundColor: badges.home.fill, color: badges.home.text }"
            aria-hidden="true"
          >
            {{ game.home_team_abbreviation }}
          </div>
          <div>
            <div class="flex items-baseline gap-1.5">
              <div
                class="font-title"
                :class="isRevealed ? (isHomeWinner ? 'text-text' : 'text-text-secondary') : 'text-text'"
              >
                {{ game.home_team_abbreviation }}
              </div>
              <!-- Remplace le "@" isolé (§10.3, signalé en recette comme
                   orphelin, flottant sur sa propre ligne) : dit l'information
                   ("qui reçoit") en toutes lettres, sans dépendre de la
                   convention NBA extérieur-puis-domicile ni de la seule
                   position. Une seule mention suffit -- sa présence sur cette
                   ligne signale déjà que l'autre équipe est l'extérieure.
                   text-disabled mesuré à 4,71:1 (sombre) / 5,20:1 (clair)
                   contre bg-surface : conforme, pas d'escalade vers
                   text-secondary nécessaire (voir §5.2 pour le cas différent
                   où text-disabled est interdit, sur --surface-info). -->
              <span class="text-[10px] font-normal uppercase tracking-wide text-text-disabled">Domicile</span>
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
      <p v-if="reliabilityCapped" data-testid="reliability-cap-note" class="mt-1 text-xs text-text-secondary">
        Confiance limitée : début de saison, notes basées sur la saison précédente.
      </p>
    </div>

    <div v-if="isRevealed" class="mt-3 border-t border-border pt-2" data-testid="win-probability">
      <p class="text-xs font-medium text-text-secondary">Probabilité de victoire · modèle expérimental, distinct de la note</p>
      <template v-if="hasProbability">
        <!-- Espacements portés par gap (une espace en tête de balise est supprimée au rendu : « CHA8 % » vu en
             recette) ; espace insécable avant « % », qui ne doit jamais partir seul à la ligne. -->
        <p class="mt-1 flex flex-wrap items-baseline gap-x-4 text-sm text-text" data-testid="win-probability-values">
          <span class="inline-flex items-baseline gap-1.5">
            <span class="font-title">{{ game.away_team_abbreviation }}</span>
            <span class="font-mono tabular-nums">{{ awayPercent }}&nbsp;%</span>
          </span>
          <span class="inline-flex items-baseline gap-1.5">
            <span class="font-title">{{ game.home_team_abbreviation }}</span>
            <span class="font-mono tabular-nums">{{ homePercent }}&nbsp;%</span>
          </span>
        </p>
        <p v-if="isUnmeasuredLevel" data-testid="win-probability-unmeasured" class="mt-1 text-xs text-text-secondary">
          À 90 % et au-delà, ce niveau n'est pas mesuré : 45 matchs seulement sur deux saisons, aux résultats
          contradictoires.
        </p>
        <p v-if="absentCount > 0" data-testid="win-probability-absents" class="mt-1 text-xs text-text-secondary">
          Ne tient pas compte des absents : {{ absentCount }} joueur{{ absentCount > 1 ? 's' : '' }}
          absent{{ absentCount > 1 ? 's' : '' }} sur ce match (la note, elle, les compte).
        </p>
      </template>
      <p v-else-if="missingPrevAbbreviations.length" data-testid="win-probability-missing" class="mt-1 text-xs text-text-secondary">
        Probabilité indisponible : écart de points de la saison précédente non renseigné pour
        {{ missingPrevAbbreviations.join(' et ') }}.
      </p>
      <p v-else data-testid="win-probability-legacy" class="mt-1 text-xs text-text-secondary">
        Probabilité non calculée pour ce pronostic (calculé avant son introduction).
      </p>
      <p v-if="gamesUsed" data-testid="win-probability-games" class="mt-1 text-xs text-text-secondary">
        Matchs terminés de la saison pris en compte : {{ game.away_team_abbreviation }} {{ gamesUsed.away }} ·
        {{ game.home_team_abbreviation }} {{ gamesUsed.home }}, plus la saison précédente.
      </p>
    </div>
  </article>
</template>
