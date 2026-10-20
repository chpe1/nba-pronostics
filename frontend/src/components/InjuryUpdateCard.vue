<script setup>
import { ref, computed } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'

// Décision d'architecture n°35 (CLAUDE.md) : pas d'indicateur avant 200 ms, au moins 300 ms une
// fois affiché, et le libellé du bouton ne change jamais -- l'indicateur est à côté, dans un
// emplacement de largeur fixe. Date.now() (pas performance.now()) : même horloge que les
// minuteries simulées des tests.
const SLOW_MS = 200
const MIN_SPINNER_MS = 300

const running = ref(false)
const showSpinner = ref(false)
const report = ref(null)
const errorMessage = ref('')

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function run() {
  if (running.value) return
  running.value = true
  errorMessage.value = ''
  let shownAt = 0
  const slowTimer = setTimeout(() => {
    shownAt = Date.now()
    showSpinner.value = true
  }, SLOW_MS)
  try {
    report.value = await apiFetch('/api/injuries/refresh', { method: 'POST' })
  } catch (error) {
    report.value = null
    // Le vrai message du serveur (ex. « Aucun rapport de blessures trouvé… »), jamais un texte générique
    // quand il y en a un.
    errorMessage.value = error instanceof ApiError ? error.message : 'Échec de la mise à jour des blessures.'
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

const STATUS_LABELS = {
  out: 'Out',
  doubtful: 'Doubtful',
  questionable: 'Questionable',
  probable: 'Probable',
  available: 'Available',
}
const statusLines = computed(() =>
  Object.entries(report.value?.status_counts ?? {}).map(([status, count]) => ({
    label: STATUS_LABELS[status] ?? status,
    count,
  })),
)
// Deux cas DISTINCTS, jamais mêlés : un joueur rattaché à une AUTRE équipe en base (transféré sans que la base
// le sache) ; un AGENT LIBRE en base (détaché de son équipe, Décision n°39 -- il n'a pas été « transféré à
// l'insu de la base », la phrase serait fausse pour lui).
const unmatchedOnOtherTeam = computed(
  () => (report.value?.unmatched ?? []).filter((u) => u.exists_in_database_on_teams.length > 0).length,
)
const unmatchedAsFreeAgent = computed(
  () => (report.value?.unmatched ?? []).filter((u) => u.exists_in_database_as_free_agent === true).length,
)

function formatDate(iso) {
  const [year, month, day] = iso.split('-')
  return `${day}/${month}/${year}`
}
const gameDatesLabel = computed(() => (report.value?.game_dates ?? []).map(formatDate).join(', ') || 'aucune lue')
</script>

<template>
  <div class="space-y-3 rounded-xl border border-border bg-surface p-4">
    <h2 class="text-sm font-semibold text-text">Blessures (rapport officiel NBA)</h2>
    <p class="text-xs text-text-secondary">
      Télécharge le rapport de blessures le plus récent publié par la NBA (PDF officiel, serveur
      ak-static.cms.nba.com), le lit, puis met à jour le statut des joueurs en base. À lancer à la
      main, quand vous le décidez : la mise à jour automatique reste désactivée.
    </p>

    <button
      type="button"
      class="flex min-h-11 items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on"
      :aria-busy="showSpinner"
      @click="run"
    >
      <span>Mettre à jour les blessures depuis la NBA</span>
      <span class="flex h-4 w-4 shrink-0 items-center justify-center" aria-hidden="true">
        <svg
          v-if="showSpinner"
          data-testid="injury-spinner"
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

    <div v-if="report" class="space-y-3 text-sm text-text">
      <p
        v-if="report.not_yet_submitted"
        role="status"
        class="rounded-lg border border-warning bg-warning/10 px-3 py-2"
      >
        <strong>Rapport non encore soumis.</strong> Les équipes n'ont rien déclaré pour les matchs
        du {{ gameDatesLabel }} (« NOT YET SUBMITTED » ×{{ report.not_yet_submitted_count }}). Ce
        n'est <strong>pas</strong> « aucun blessé ». Aucune écriture n'a été faite en base.
      </p>
      <p
        v-else-if="report.entries_read === 0"
        role="status"
        class="rounded-lg border border-warning bg-warning/10 px-3 py-2"
      >
        <strong>Le rapport ne contient aucune entrée.</strong> Aucune écriture n'a été faite en base.
      </p>
      <p
        v-else-if="report.not_yet_submitted_count > 0"
        role="status"
        class="rounded-lg bg-surface-info px-3 py-2 text-text-secondary"
      >
        Rapport partiel : {{ report.not_yet_submitted_count }} mention(s) « NOT YET SUBMITTED » —
        les joueurs de ces équipes ne figurent pas dans les chiffres ci-dessous.
      </p>

      <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt class="text-text-secondary">Rapport</dt>
        <dd class="break-all">
          <a :href="report.report_url" target="_blank" rel="noopener noreferrer" class="underline underline-offset-2">{{
            report.report_url
          }}</a>
        </dd>
        <dt class="text-text-secondary">Publié le</dt>
        <dd>{{ report.report_time_new_york }}<br />{{ report.report_time_paris }}</dd>
        <dt class="text-text-secondary">Matchs couverts</dt>
        <dd>{{ gameDatesLabel }}</dd>
        <dt class="text-text-secondary">Entrées lues</dt>
        <dd>{{ report.entries_read }}</dd>
        <dt class="text-text-secondary">Rattachées</dt>
        <dd>{{ report.matched_count }}</dd>
        <dt class="text-text-secondary">Non rattachées</dt>
        <dd>{{ report.unmatched_count }}</dd>
        <dt class="text-text-secondary">Écriture en base</dt>
        <dd>{{ report.written ? 'oui' : 'non' }}</dd>
      </dl>

      <div v-if="statusLines.length">
        <h3 class="font-medium">Statuts appliqués</h3>
        <ul class="mt-1 flex flex-wrap gap-x-4 gap-y-1">
          <li v-for="line in statusLines" :key="line.label">{{ line.label }} : {{ line.count }}</li>
        </ul>
        <p class="mt-2">
          Absents (Out + Doubtful) : <strong>{{ report.absent_count }}</strong>, dont
          <strong>{{ report.weighing_count }}</strong> au-dessus du seuil de
          {{ report.mpg_threshold }} min/match : ceux-là pèseront réellement dans un calcul.
        </p>
        <ul v-if="report.weighing.length" class="mt-1 space-y-0.5 text-text-secondary">
          <li v-for="player in report.weighing" :key="player.team_abbreviation + player.name">
            {{ player.name }} ({{ player.team_abbreviation }}) — {{ player.status }}, PER
            {{ player.per.toFixed(1) }}, {{ player.mpg.toFixed(1) }} min
          </li>
        </ul>
      </div>

      <div v-if="report.unmatched.length">
        <h3 class="font-medium">
          {{ report.unmatched.length }} entrée(s) non rattachée(s) à un joueur de la base
        </h3>
        <p class="mt-1 text-text-secondary" data-testid="unmatched-summary">
          <span v-if="unmatchedOnOtherTeam">
            Dont <strong>{{ unmatchedOnOtherTeam }}</strong> existent en base mais sous une autre
            équipe que celle du rapport (joueur transféré sans que la base le sache).
          </span>
          <span v-if="unmatchedAsFreeAgent">
            Dont <strong>{{ unmatchedAsFreeAgent }}</strong> existent en base comme agent(s) libre(s)
            (détaché(s) de leur équipe lors d'un import d'effectif : à replacer dans une équipe depuis
            l'écran Joueurs pour que leur statut s'applique).
          </span>
          <span v-if="!unmatchedOnOtherTeam && !unmatchedAsFreeAgent">
            Aucun n'existe en base sous un autre nom d'équipe ni comme agent libre.
          </span>
        </p>
        <ul class="mt-2 space-y-0.5">
          <li v-for="(entry, index) in report.unmatched" :key="index">
            {{ entry.player_name_raw }} — {{ entry.team_abbreviation || entry.team_raw }}
            <span class="text-text-secondary">({{ entry.status_raw }})</span>
            <span v-if="entry.exists_in_database_on_teams.length" class="text-text-secondary">
              — en base sous : {{ entry.exists_in_database_on_teams.join(', ') }}
            </span>
            <span v-if="entry.exists_in_database_as_free_agent" class="text-text-secondary">
              — en base comme agent libre
            </span>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
