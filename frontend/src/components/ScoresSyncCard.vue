<script setup>
import { ref, computed } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'

// Décision d'architecture n°35 (CLAUDE.md) : pas d'indicateur avant 200 ms, au moins 300 ms une fois
// affiché, libellé du bouton jamais remplacé (l'indicateur est à côté, dans un emplacement de largeur
// fixe). Même forme que InjuryUpdateCard.vue.
const SLOW_MS = 200
const MIN_SPINNER_MS = 300
// Plage par défaut : les 3 derniers jours jusqu'à aujourd'hui (dates NBA). Couvre « je reviens de trois
// jours d'absence » ET la fenêtre habituelle de la tâche planifiée (hier + aujourd'hui) ; un seul appel API.
const DEFAULT_LOOKBACK_DAYS = 3

// Date NBA du jour (US/ET) : jamais la date UTC ni celle du navigateur (limitation n°35).
function nbaToday() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York' }).format(new Date())
}
function shiftDays(iso, days) {
  const [y, m, d] = iso.split('-').map(Number)
  const shifted = new Date(Date.UTC(y, m - 1, d + days))
  return shifted.toISOString().slice(0, 10)
}

const dateTo = ref(nbaToday())
const dateFrom = ref(shiftDays(dateTo.value, -DEFAULT_LOOKBACK_DAYS))

const running = ref(false)
const showSpinner = ref(false)
const report = ref(null)
const errorMessage = ref('')

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function run() {
  if (running.value) return
  if (dateFrom.value && dateTo.value && dateFrom.value > dateTo.value) {
    errorMessage.value = 'La date de début doit précéder ou égaler la date de fin.'
    return
  }
  running.value = true
  errorMessage.value = ''
  let shownAt = 0
  const slowTimer = setTimeout(() => {
    shownAt = Date.now()
    showSpinner.value = true
  }, SLOW_MS)
  try {
    const query = new URLSearchParams({ date_from: dateFrom.value, date_to: dateTo.value })
    report.value = await apiFetch(`/api/scores/sync?${query}`, { method: 'POST' })
  } catch (error) {
    report.value = null
    // Le vrai message du serveur (ex. « balldontlie a répondu 429 … »), jamais un texte générique quand il y en a un.
    errorMessage.value = error instanceof ApiError ? error.message : 'Échec de la synchronisation des scores.'
  } finally {
    clearTimeout(slowTimer)
    if (showSpinner.value) {
      const remaining = MIN_SPINNER_MS - (Date.now() - shownAt)
      if (remaining > 0) await sleep(remaining)
    }
    showSpinner.value = false
    running.value = false
  }
}

function formatDate(iso) {
  const [year, month, day] = iso.split('-')
  return `${day}/${month}/${year}`
}
const rangeLabel = computed(() => {
  if (!report.value) return ''
  const { date_from: from, date_to: to } = report.value
  return from === to ? formatDate(from) : `${formatDate(from)} au ${formatDate(to)}`
})
const nothingChanged = computed(() => report.value && !report.value.written)
const STATUS_LABELS = { scheduled: 'à venir', finished: 'terminé', postponed: 'reporté' }
const statusLabel = (status) => STATUS_LABELS[status] ?? status
const daysWithContent = computed(() => (report.value?.days ?? []).filter((d) => d.found > 0))
</script>

<template>
  <div class="space-y-3 rounded-xl border border-border bg-surface p-4">
    <h2 class="text-sm font-semibold text-text">Scores des matchs (balldontlie.io)</h2>
    <p class="text-xs text-text-secondary">
      Récupère les résultats des matchs terminés sur la plage choisie et les enregistre. À utiliser
      après une absence : la synchronisation automatique ne rattrape aucun créneau manqué et ne lit
      que la veille et le jour. Dates NBA (heure de New York).
    </p>

    <div class="grid grid-cols-2 gap-3">
      <label class="block text-xs font-medium text-text">
        Du
        <input
          v-model="dateFrom"
          type="date"
          data-testid="scores-date-from"
          class="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text"
        />
      </label>
      <label class="block text-xs font-medium text-text">
        Au
        <input
          v-model="dateTo"
          type="date"
          data-testid="scores-date-to"
          class="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text"
        />
      </label>
    </div>

    <button
      type="button"
      class="flex min-h-11 items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on"
      :aria-busy="showSpinner"
      @click="run"
    >
      <span>Synchroniser les scores</span>
      <span class="flex h-4 w-4 shrink-0 items-center justify-center" aria-hidden="true">
        <svg
          v-if="showSpinner"
          data-testid="scores-spinner"
          viewBox="0 0 20 20"
          class="h-4 w-4 animate-spin motion-reduce:animate-none"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
        >
          <path d="M10 3a7 7 0 1 0 7 7" />
        </svg>
      </span>
    </button>

    <p v-if="errorMessage" role="alert" class="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">
      {{ errorMessage }}
    </p>

    <div v-if="report" class="space-y-3 text-sm text-text" data-testid="scores-report">
      <p
        v-if="nothingChanged"
        role="status"
        data-testid="scores-nothing-changed"
        class="rounded-lg bg-surface-info px-3 py-2 text-text-secondary"
      >
        <strong class="text-text">Rien n'a changé en base.</strong>
        <template v-if="report.found === 0"> L'API ne renvoie aucun match sur {{ rangeLabel }}.</template>
        <template v-else>
          Les {{ report.found }} match(s) trouvé(s) étaient déjà à jour, pas encore terminés ou ignorés
          (détail ci-dessous). Aucune écriture n'a été faite.
        </template>
      </p>

      <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt class="text-text-secondary">Plage</dt>
        <dd>{{ rangeLabel }} ({{ report.days_count }} jour(s))</dd>
        <dt class="text-text-secondary">Matchs trouvés</dt>
        <dd data-testid="scores-found">{{ report.found }}</dd>
        <dt class="text-text-secondary">Enregistrés (passés en terminé)</dt>
        <dd data-testid="scores-recorded">
          <strong>{{ report.recorded_count }}</strong>
        </dd>
        <dt class="text-text-secondary">Déjà à jour, non retouchés</dt>
        <dd data-testid="scores-already-final">{{ report.already_final_count }}</dd>
        <dt class="text-text-secondary">Pas encore terminés</dt>
        <dd data-testid="scores-not-finished">{{ report.not_finished_count }}</dd>
        <dt v-if="report.status_change_count" class="text-text-secondary">Changements de statut</dt>
        <dd v-if="report.status_change_count">{{ report.status_change_count }}</dd>
        <dt class="text-text-secondary">Ignorés</dt>
        <dd data-testid="scores-skipped">{{ report.skipped_count }}</dd>
        <dt class="text-text-secondary">Écriture en base</dt>
        <dd data-testid="scores-written">{{ report.written ? 'oui' : 'non' }}</dd>
      </dl>

      <div v-if="report.recorded_count">
        <h3 class="font-medium">Matchs enregistrés</h3>
        <ul class="mt-1 space-y-0.5" data-testid="scores-recorded-list">
          <template v-for="day in report.days" :key="day.date">
            <li v-for="game in day.recorded" :key="game.game_id">
              {{ game.away_team_name }} {{ game.away_score }} – {{ game.home_score }} {{ game.home_team_name }}
              <span class="text-text-secondary">({{ formatDate(day.date) }}<template v-if="game.correction">, score corrigé</template>)</span>
            </li>
          </template>
        </ul>
      </div>

      <div v-if="report.status_change_count">
        <h3 class="font-medium">Changements de statut</h3>
        <ul class="mt-1 space-y-0.5">
          <template v-for="day in report.days" :key="day.date">
            <li v-for="change in day.status_changes" :key="change.game_id">
              {{ change.away_team_name }} @ {{ change.home_team_name }} :
              {{ statusLabel(change.previous_status) }} → {{ statusLabel(change.new_status) }}
            </li>
          </template>
        </ul>
      </div>

      <div v-if="report.skipped_count">
        <h3 class="font-medium">Ignorés ({{ report.skipped_count }})</h3>
        <ul class="mt-1 space-y-0.5" data-testid="scores-skipped-list">
          <template v-for="day in report.days" :key="day.date">
            <li v-for="(skipped, index) in day.skipped" :key="day.date + index">
              {{ skipped.label }} ({{ formatDate(day.date) }}) —
              <span class="text-text-secondary">{{ skipped.reason_label }}</span>
            </li>
          </template>
        </ul>
      </div>

      <div v-if="daysWithContent.length > 1 || (report.days.length > 1 && report.found)">
        <h3 class="font-medium">Par date</h3>
        <ul class="mt-1 space-y-0.5 text-text-secondary" data-testid="scores-days">
          <li v-for="day in report.days" :key="day.date">
            {{ formatDate(day.date) }} : {{ day.found }} trouvé(s), {{ day.recorded_count }} enregistré(s),
            {{ day.already_final_count }} déjà à jour, {{ day.not_finished_count }} pas terminé(s)<template
              v-if="day.skipped_count"
              >, {{ day.skipped_count }} ignoré(s)</template
            >
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
