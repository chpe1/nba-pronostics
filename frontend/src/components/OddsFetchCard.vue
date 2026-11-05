<script setup>
import { ref, computed } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'
import {
  formatLocalDateTime,
  isBalanceCheck,
  reasonLabel,
  UNMATCHED_REASONS,
  IGNORED_REASONS,
  NO_ODDS_REASONS,
  ANOMALY_REASONS,
} from '@/utils/oddsFetchFormat'

const props = defineProps({ status: { type: Object, default: null } })
const emit = defineEmits(['fetched'])

// Décision d'architecture n°35 : pas d'indicateur avant 200 ms, au moins 300 ms une fois affiché, libellé du bouton
// jamais remplacé (même forme que ScoresSyncCard.vue).
const SLOW_MS = 200
const MIN_SPINNER_MS = 300

const running = ref(false)
const showSpinner = ref(false)
const buttonRun = ref(null)
const errorMessage = ref('')

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function run() {
  if (running.value) return // garde en code, pas `disabled` (n°35) : un double clic ne coûte pas deux crédits
  running.value = true
  errorMessage.value = ''
  let shownAt = 0
  const slowTimer = setTimeout(() => {
    shownAt = Date.now()
    showSpinner.value = true
  }, SLOW_MS)
  try {
    buttonRun.value = await apiFetch('/api/odds/fetch', { method: 'POST' })
  } catch (error) {
    buttonRun.value = null
    // Le vrai message de l'API (clé déjà masquée côté serveur), jamais un texte générique quand il y en a un.
    errorMessage.value = error instanceof ApiError ? error.message : 'Échec du relevé des cotes.'
  } finally {
    clearTimeout(slowTimer)
    if (showSpinner.value) {
      const remaining = MIN_SPINNER_MS - (Date.now() - shownAt)
      if (remaining > 0) await sleep(remaining)
    }
    showSpinner.value = false
    running.value = false
    emit('fetched') // l'écran recharge les cases, l'état et le journal (même après un échec : il est journalisé)
  }
}

const shownRun = computed(() => buttonRun.value ?? props.status?.latest_run ?? null)
const report = computed(() => {
  const r = shownRun.value
  return r && !isBalanceCheck(r) && !r.error ? r.report : null
})
const taskText = computed(() => {
  const s = props.status
  if (!s) return ''
  if (!s.api_key_configured) return "La clé de l'API n'est pas configurée sur le serveur."
  if (!s.scheduler_enabled) {
    return 'Relevé horaire automatique désactivé (ENABLE_ODDS_SCHEDULER) : seul le bouton relève les cotes.'
  }
  if (s.scheduled_suspended) {
    return `Relevé horaire SUSPENDU : ${s.last_known_credits} crédit(s) restant(s), sous le seuil de ${s.credits_threshold}. Il reprendra seul quand le solde remontera ; le bouton reste utilisable.`
  }
  return "Relevé horaire actif tant qu'un match commence dans les 3 heures (le PC et le serveur doivent être allumés)."
})
const runKind = (run) => (run.trigger === 'button' ? 'bouton' : 'tâche planifiée')
const runSummary = (run) => {
  if (isBalanceCheck(run)) return 'relecture gratuite du solde'
  if (run.error) return `ÉCHEC${run.http_status ? ` (HTTP ${run.http_status})` : ''}`
  return `${run.events_returned} match(s) renvoyé(s), ${run.matched_count} reconnu(s), ${run.unmatched_count} non reconnu(s), ${run.rows_written} cote(s) écrite(s)`
}
const alertGaps = computed(() => (report.value?.time_gaps ?? []).filter((g) => g.alert))
</script>

<template>
  <div class="space-y-3 rounded-xl border border-border bg-surface p-4" data-testid="odds-fetch-card">
    <h2 class="text-sm font-semibold text-text">Relevé automatique (the-odds-api.com)</h2>
    <p class="text-xs text-text-secondary">
      Un relevé coûte 1 crédit (500 par mois). Chaque cote lue est ajoutée à l'historique, marquée « auto » avec
      son heure ; une saisie à la main reste possible et marquée « manuel ».
    </p>

    <div v-if="status" class="space-y-1 text-xs text-text-secondary" data-testid="odds-fetch-status">
      <p>
        Crédits restants :
        <strong class="text-text" data-testid="odds-credits">{{ status.last_known_credits ?? 'inconnu' }}</strong>
        <template v-if="status.last_known_credits_at">
          (au {{ formatLocalDateTime(status.last_known_credits_at) }})
        </template>
      </p>
      <p data-testid="odds-task-state">{{ taskText }}</p>
    </div>

    <button
      type="button"
      class="flex min-h-11 items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on"
      :aria-busy="showSpinner"
      data-testid="odds-fetch-button"
      @click="run"
    >
      <span>Relever les cotes maintenant</span>
      <span class="flex h-4 w-4 shrink-0 items-center justify-center" aria-hidden="true">
        <svg
          v-if="showSpinner"
          data-testid="odds-fetch-spinner"
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

    <p
      v-if="errorMessage"
      role="alert"
      data-testid="odds-fetch-error"
      class="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text"
    >
      {{ errorMessage }}
    </p>

    <div v-if="report" class="space-y-2 text-sm text-text" data-testid="odds-fetch-report">
      <p class="text-xs text-text-secondary">
        Dernier relevé : {{ formatLocalDateTime(shownRun.fetched_at) }} ({{ runKind(shownRun) }}) —
        <span data-testid="odds-report-counts">{{ runSummary(shownRun) }}</span
        ><template v-if="shownRun.credits_used !== null">, {{ shownRun.credits_used }} crédit(s) consommé(s)</template>.
      </p>

      <div v-if="report.unmatched.length" data-testid="odds-report-unmatched">
        <p class="font-medium text-danger-text">Non reconnus ({{ report.unmatched.length }}) — rien n'a été deviné :</p>
        <ul class="list-disc pl-5 text-xs">
          <li v-for="(item, i) in report.unmatched" :key="i">
            {{ item.away_team }} @ {{ item.home_team }} : {{ reasonLabel(UNMATCHED_REASONS, item.reason) }}
            <template v-if="item.unknown_labels?.length">({{ item.unknown_labels.join(', ') }})</template>
          </li>
        </ul>
      </div>

      <div v-if="report.no_odds_yet.length" data-testid="odds-report-no-odds">
        <p class="font-medium">Sans cote pour l'instant ({{ report.no_odds_yet.length }}) :</p>
        <ul class="list-disc pl-5 text-xs">
          <li v-for="(item, i) in report.no_odds_yet" :key="i">
            {{ item.label }} : {{ reasonLabel(NO_ODDS_REASONS, item.reason) }}
          </li>
        </ul>
      </div>

      <div v-if="alertGaps.length" data-testid="odds-report-time-gaps">
        <p class="font-medium text-danger-text">Coup d'envoi annoncé plus tôt que notre calendrier&nbsp;:</p>
        <ul class="list-disc pl-5 text-xs">
          <li v-for="g in alertGaps" :key="g.game_id">{{ g.label }} : {{ -g.gap_minutes }} min plus tôt</li>
        </ul>
      </div>

      <div v-if="report.ignored.length" data-testid="odds-report-ignored">
        <p class="font-medium">Ignorés ({{ report.ignored.length }}) :</p>
        <ul class="list-disc pl-5 text-xs">
          <li v-for="(item, i) in report.ignored" :key="i">
            {{ item.label }} : {{ reasonLabel(IGNORED_REASONS, item.reason) }}
          </li>
        </ul>
      </div>

      <div v-if="report.anomalies.length" data-testid="odds-report-anomalies">
        <p class="font-medium">Anomalies de données ({{ report.anomalies.length }}) :</p>
        <ul class="list-disc pl-5 text-xs">
          <li v-for="(item, i) in report.anomalies" :key="i">
            {{ item.label }}, {{ item.bookmaker }} : {{ reasonLabel(ANOMALY_REASONS, item.reason) }}
          </li>
        </ul>
      </div>

      <p v-if="report.matched.length" class="text-xs text-text-secondary" data-testid="odds-report-matched">
        Reconnus ({{ report.matched.length }}) :
        {{
          report.matched
            .map(
              (m) =>
                `${m.label} (${m.rows} cote(s)${m.missing_screen_bookmakers.length ? `, manque ${m.missing_screen_bookmakers.join(' et ')}` : ''})`,
            )
            .join(', ')
        }}
      </p>
    </div>

    <details v-if="status?.recent_runs?.length" class="text-xs text-text-secondary" data-testid="odds-fetch-journal">
      <summary class="min-h-11 cursor-pointer py-3 text-text">
        Journal des appels ({{ status.recent_runs.length }} derniers)
      </summary>
      <ul class="space-y-1">
        <li v-for="run in status.recent_runs" :key="run.id" :data-testid="`odds-run-${run.id}`">
          {{ formatLocalDateTime(run.fetched_at) }} · {{ runKind(run) }} · {{ runSummary(run) }}
          <template v-if="run.credits_remaining !== null"> · reste {{ run.credits_remaining }}</template>
          <span v-if="run.error" class="text-danger-text"> · {{ run.error }}</span>
        </li>
      </ul>
    </details>
  </div>
</template>
