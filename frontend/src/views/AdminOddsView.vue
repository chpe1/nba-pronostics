<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'
import {
  impliedProbability,
  bookmakerMarginPct,
  noMarginProbabilities,
  bestOdds,
  parseOddsInput,
  formatOddsFr,
} from '@/utils/oddsMarket'
import { COLLECTION_LABELS, formatLocalTime } from '@/utils/oddsFetchFormat'
import OddsFetchCard from '@/components/OddsFetchCard.vue'
import KickoffAlertsBanner from '@/components/KickoffAlertsBanner.vue'

// `source` = l'identifiant EXACT du bookmaker chez the-odds-api.com (winamax_fr, unibet_fr) : c'est lui qui rend
// comparables une saisie à la main et un relevé automatique du même bookmaker (renommage du 2026-11-03).
// Les 4 colonnes de saisie, dans l'ordre visuel ET dans l'ordre de tabulation (voir assignTabIndex) --
// un seul tableau, jamais deux listes à tenir synchronisées.
const COLUMNS = [
  { key: 'winamax_home', source: 'winamax_fr', side: 'home', label: 'Winamax — domicile' },
  { key: 'winamax_away', source: 'winamax_fr', side: 'away', label: 'Winamax — extérieur' },
  { key: 'unibet_home', source: 'unibet_fr', side: 'home', label: 'Unibet — domicile' },
  { key: 'unibet_away', source: 'unibet_fr', side: 'away', label: 'Unibet — extérieur' },
]

function nowAsLocalInputValue() {
  // Contrairement à Game.game_date (heure murale US/ET, voir AdminGamesView.vue), recorded_at est un
  // instant RÉEL quelconque -- l'heure LOCALE du navigateur, pas new Date().toISOString() (qui donnerait
  // l'heure UTC, lue à tort comme une heure locale par le champ datetime-local).
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const selectedDate = ref(new Date().toISOString().slice(0, 10))
const recordedAtLocal = ref(nowAsLocalInputValue())
const games = ref([])
const forms = reactive({})
// Détail d'un refus/skip du dernier enregistrement, par cellule -- survit au rechargement qui suit
// (voir save()), pour que la raison reste visible même une fois les champs sans problème rafraîchis.
const cellIssues = reactive({})

const isLoading = ref(false)
const isSaving = ref(false)
const errorMessage = ref('')
const loadFailed = ref(false)
const saveSummary = ref('')
// État du relevé automatique (GET /api/odds/fetch-status) : crédits, journal, alertes d'heure de coup d'envoi.
// Son échec ne bloque jamais la saisie à la main : l'écran reste utilisable sans lui.
const fetchStatus = ref(null)

function emptyForm() {
  return { winamax_home: '', winamax_away: '', unibet_home: '', unibet_away: '' }
}

function fillForm(game) {
  const form = emptyForm()
  for (const col of COLUMNS) {
    form[col.key] = formatOddsFr(game[col.key].value)
  }
  return form
}

async function loadOdds({ keepIssuedCells = false } = {}) {
  isLoading.value = true
  errorMessage.value = ''
  loadFailed.value = false
  try {
    const data = await apiFetch(`/api/odds?date=${selectedDate.value}`)
    games.value = data.games
    for (const game of data.games) {
      const fresh = fillForm(game)
      if (keepIssuedCells) {
        // Une cellule refusée/ignorée au dernier essai garde ce que l'utilisateur avait tapé (pour
        // qu'il puisse la corriger sans tout retaper) -- toutes les autres reprennent la valeur confirmée
        // par le serveur.
        const existing = forms[game.id] || emptyForm()
        for (const col of COLUMNS) {
          const key = `${game.id}_${col.key}`
          if (!cellIssues[key]) fresh[col.key] = fresh[col.key] || existing[col.key]
        }
      }
      forms[game.id] = fresh
    }
  } catch (error) {
    games.value = []
    loadFailed.value = true
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les cotes.'
  } finally {
    isLoading.value = false
  }
}

// Ordre de tabulation en COLONNE (une bookmaker-colonne entière, de haut en bas, avant la suivante) --
// jamais ligne par ligne. 1 = l'heure du relevé (en tête, avant toute cellule) ; 2..(4N+1) = les 4N
// cellules, colonne par colonne ; 4N+2 = Enregistrer. games.value doit être déjà chargé pour ce calcul.
function cellTabIndex(gameIndex, colIndex) {
  const n = games.value.length
  return 2 + colIndex * n + gameIndex
}
const saveTabIndex = computed(() => 2 + COLUMNS.length * games.value.length)

function marketFor(game) {
  const form = forms[game.id]
  if (!form) return null
  const read = (key) => parseOddsInput(form[key])
  const bySource = {}
  let hasAnyValue = false
  for (const source of ['winamax', 'unibet']) {
    const home = read(`${source}_home`)
    const away = read(`${source}_away`)
    if (home !== null || away !== null) hasAnyValue = true
    const probHome = impliedProbability(home)
    const probAway = impliedProbability(away)
    bySource[source] = {
      probHome,
      probAway,
      marginPct: bookmakerMarginPct(probHome, probAway),
      noMargin: noMarginProbabilities(probHome, probAway),
    }
  }
  // Rien de saisi pour ce match : pas de ligne « Marché » à afficher (plutôt qu'une ligne vide, bruit
  // visuel sans information -- repéré sur les captures du 2026-10-24).
  if (!hasAnyValue) return null
  return {
    bySource,
    bestHome: bestOdds(read('winamax_home'), read('unibet_home')),
    bestAway: bestOdds(read('winamax_away'), read('unibet_away')),
  }
}

function cellTeamAbbr(game, col) {
  // Lève l'ambiguïté domicile/extérieur : la case elle-même porte l'abréviation de l'équipe concernée
  // (ex. ligne « MIA @ CHA » -> CHA, MIA, CHA, MIA), plutôt que de compter sur une lecture correcte des
  // en-têtes de colonne (qui disent le bookmaker et le côté, pas l'équipe). Remplace aussi le texte
  // d'exemple « 1,85 », répété 44 fois, qui donnait à tort l'impression d'un formulaire prérempli.
  return col.side === 'home' ? game.home_team_abbreviation : game.away_team_abbreviation
}

function gameTimeLabel(isoGameDate) {
  // game_date est une heure murale US/ET naïve (Décision n°3) : mêmes composants, jamais convertis
  // (voir GameCard.vue::gameTime, même libellé " · New York").
  const timePart = (isoGameDate.split('T')[1] || '00:00:00').slice(0, 5)
  return timePart
}

async function loadFetchStatus() {
  try {
    fetchStatus.value = await apiFetch('/api/odds/fetch-status')
  } catch {
    fetchStatus.value = null
  }
}

async function onFetched() {
  await Promise.all([loadOdds({ keepIssuedCells: true }), loadFetchStatus()])
}

function cellOrigin(game, col) {
  // « auto 14:05 » / « manuel 14:05 » : l'origine et l'heure du DERNIER relevé de la case, quel qu'il soit.
  const cell = game[col.key]
  if (!cell?.recorded_at || !cell.collection) return ''
  return `${COLLECTION_LABELS[cell.collection]} ${formatLocalTime(cell.recorded_at)}`
}

async function save() {
  errorMessage.value = ''
  saveSummary.value = ''
  for (const key of Object.keys(cellIssues)) delete cellIssues[key]
  isSaving.value = true
  try {
    const entries = []
    for (const game of games.value) {
      if (game.started) continue
      const form = forms[game.id]
      for (const col of COLUMNS) {
        const raw = form[col.key].trim()
        if (raw === '') continue
        entries.push({ game_id: game.id, side: col.side, source: col.source, value: raw })
      }
    }
    if (entries.length === 0) {
      saveSummary.value = 'Rien à enregistrer : toutes les cases sont vides.'
      return
    }
    const recordedAtUtc = new Date(recordedAtLocal.value).toISOString()
    const result = await apiFetch('/api/odds', { method: 'POST', body: { recorded_at: recordedAtUtc, entries } })

    for (const entry of result.entries) {
      if (entry.outcome === 'rejected' || entry.outcome === 'skipped_started') {
        cellIssues[`${entry.game_id}_${entry.source}_${entry.side}`] = entry.detail
      }
    }
    const writtenCount = result.created_count + result.updated_count
    const parts = [`${writtenCount} cote(s) enregistrée(s)`]
    if (result.unchanged_count) parts.push(`${result.unchanged_count} déjà identique(s)`)
    if (result.rejected_count) parts.push(`${result.rejected_count} refusée(s)`)
    if (result.skipped_count) parts.push(`${result.skipped_count} non saisissable(s) (coup d'envoi passé)`)
    saveSummary.value = parts.join(', ') + '.'

    await loadOdds({ keepIssuedCells: true })
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Échec de l'enregistrement."
  } finally {
    isSaving.value = false
  }
}

function issueFor(gameId, col) {
  return cellIssues[`${gameId}_${col.source}_${col.side}`]
}

onMounted(() => {
  loadOdds()
  loadFetchStatus()
})
</script>

<template>
  <section class="mx-auto max-w-5xl space-y-4 px-4 py-6">
    <h1 class="text-xl font-semibold text-text">Saisie des cotes</h1>
    <p class="text-sm text-text-secondary">
      Cet écran sert à relever les cotes (à la main ou automatiquement) pour les comparer plus tard au moteur ;
      il ne calcule aucune value. Une cote non relevée avant le coup d'envoi est perdue définitivement. L'historique complet est conservé — un nouveau
      relevé s'ajoute, il n'efface jamais le précédent.
    </p>

    <KickoffAlertsBanner :alerts="fetchStatus?.alerts ?? []" />
    <OddsFetchCard :status="fetchStatus" @fetched="onFetched" />

    <div class="flex flex-wrap items-end gap-4">
      <div>
        <label for="odds-date" class="mb-1 block text-xs font-medium text-text">Date des matchs</label>
        <input
          id="odds-date"
          v-model="selectedDate"
          type="date"
          class="min-h-11 rounded-lg border border-border px-3 py-2 text-sm"
          @change="loadOdds()"
        />
      </div>
      <div>
        <label for="odds-recorded-at" class="mb-1 block text-xs font-medium text-text">
          Instant du relevé
        </label>
        <input
          id="odds-recorded-at"
          v-model="recordedAtLocal"
          type="datetime-local"
          tabindex="1"
          class="min-h-11 rounded-lg border border-border px-3 py-2 text-sm"
        />
        <p class="mt-1 max-w-xs text-xs text-text-secondary">
          Par défaut l'instant présent — à corriger si les cotes saisies ont été relevées plus tôt.
        </p>
      </div>
    </div>

    <p v-if="errorMessage && !loadFailed" role="alert" class="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">
      {{ errorMessage }}
    </p>
    <p v-if="saveSummary" class="rounded-lg bg-success/10 px-3 py-2 text-sm text-success" data-testid="save-summary">
      {{ saveSummary }}
    </p>
    <p v-if="isLoading" class="text-sm text-text-secondary">Chargement…</p>

    <div v-else-if="loadFailed" role="alert" class="rounded-lg bg-danger/10 p-3">
      <p class="text-sm text-danger-text">{{ errorMessage }}</p>
      <button
        type="button"
        class="mt-3 min-h-11 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
        :disabled="isLoading"
        @click="loadOdds()"
      >
        Réessayer
      </button>
    </div>

    <p v-else-if="games.length === 0" class="text-sm text-text-secondary">Aucun match ce jour-là.</p>

    <form v-else class="space-y-4" @submit.prevent="save">
      <!-- Défilement horizontal du seul tableau (jamais de la page) : à 390px, la structure en colonnes
           reste identique -- indispensable pour que l'ordre de tabulation par colonne reste lisible à
           toute largeur, plutôt qu'un empilement qui le ferait paraître « sauter » visuellement. -->
      <div class="overflow-x-auto rounded-xl border border-border">
        <table class="w-full min-w-[840px] border-collapse text-sm">
          <thead>
            <tr class="border-b border-border bg-surface-sunken text-left text-xs font-medium text-text-secondary">
              <th class="p-3">Match</th>
              <th v-for="col in COLUMNS" :key="col.key" class="p-3">{{ col.label }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(game, gameIndex) in games" :key="game.id">
              <tr class="border-b border-border/50">
                <td class="p-3 align-top">
                  <div class="font-medium text-text">{{ game.away_team_abbreviation }} @ {{ game.home_team_abbreviation }}</div>
                  <div class="text-xs text-text-secondary">
                    {{ gameTimeLabel(game.game_date) }}<span> · New York</span>
                  </div>
                  <p v-if="game.started" class="mt-1 text-xs text-warning" data-testid="started-explanation">
                    Coup d'envoi déjà passé : non saisissable.
                  </p>
                </td>
                <td v-for="(col, colIndex) in COLUMNS" :key="col.key" class="p-3 align-top">
                  <input
                    v-model="forms[game.id][col.key]"
                    type="text"
                    inputmode="decimal"
                    :disabled="game.started"
                    :tabindex="game.started ? -1 : cellTabIndex(gameIndex, colIndex)"
                    :aria-label="`${col.label} — ${game.away_team_abbreviation} @ ${game.home_team_abbreviation}`"
                    :placeholder="cellTeamAbbr(game, col)"
                    class="min-h-11 w-24 rounded-lg border border-border px-3 py-2 text-sm disabled:opacity-50"
                    :data-testid="`cell-${game.id}-${col.key}`"
                  />
                  <p
                    v-if="cellOrigin(game, col)"
                    class="mt-1 text-xs text-text-secondary"
                    :data-testid="`origin-${game.id}-${col.key}`"
                  >
                    {{ cellOrigin(game, col) }}
                  </p>
                  <p v-if="issueFor(game.id, col)" class="mt-1 max-w-[9rem] text-xs text-danger-text">
                    {{ issueFor(game.id, col) }}
                  </p>
                </td>
              </tr>
              <!-- Ligne d'information, calculée en direct à partir de ce qui est tapé -- jamais envoyée au
                   serveur, jamais une valeur de pronostic (aucun calcul de value, voir CLAUDE.md). -->
              <tr v-if="marketFor(game)" class="border-b border-border bg-surface-sunken/50 text-xs text-text-secondary">
                <td class="p-3 align-top">Marché</td>
                <td v-for="source in ['winamax', 'unibet']" :key="source" colspan="2" class="p-3 align-top">
                  <template v-if="marketFor(game).bySource[source].marginPct !== null">
                    <div>Marge {{ source }} : <span class="font-medium text-text">{{ marketFor(game).bySource[source].marginPct.toFixed(2) }} %</span></div>
                    <div>
                      Sans marge : dom. {{ (marketFor(game).bySource[source].noMargin.home * 100).toFixed(1) }} % /
                      ext. {{ (marketFor(game).bySource[source].noMargin.away * 100).toFixed(1) }} %
                    </div>
                  </template>
                  <template v-else>
                    <div v-if="marketFor(game).bySource[source].probHome !== null">
                      Dom. : implicite {{ (marketFor(game).bySource[source].probHome * 100).toFixed(1) }} %
                    </div>
                    <div v-if="marketFor(game).bySource[source].probAway !== null">
                      Ext. : implicite {{ (marketFor(game).bySource[source].probAway * 100).toFixed(1) }} %
                    </div>
                  </template>
                </td>
              </tr>
              <tr v-if="marketFor(game) && (marketFor(game).bestHome !== null || marketFor(game).bestAway !== null)" class="border-b border-border bg-surface-sunken/50 text-xs text-text-secondary">
                <td class="p-3 pt-0 align-top"></td>
                <td colspan="4" class="p-3 pt-0 align-top">
                  Meilleure cote — domicile :
                  <span class="font-medium text-text">{{ marketFor(game).bestHome !== null ? marketFor(game).bestHome.toFixed(2).replace('.', ',') : '—' }}</span>
                  · extérieur :
                  <span class="font-medium text-text">{{ marketFor(game).bestAway !== null ? marketFor(game).bestAway.toFixed(2).replace('.', ',') : '—' }}</span>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <p class="text-xs text-text-secondary">
        Les cases vides sont ignorées — seules les cases remplies sont enregistrées. Virgule ou point, les
        deux sont acceptés. Entrée valide et enregistre directement depuis n'importe quel champ.
      </p>

      <button
        type="submit"
        :tabindex="saveTabIndex"
        class="min-h-11 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
        :disabled="isSaving"
      >
        {{ isSaving ? 'Enregistrement…' : 'Enregistrer' }}
      </button>
    </form>
  </section>
</template>
