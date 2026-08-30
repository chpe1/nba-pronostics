<script setup>
import { ref, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'

const counts = ref(null)
const audit = ref(null)
const errorMessage = ref('')
const isAuditing = ref(false)

const TABLE_LABELS = {
  team_count: 'Équipes',
  player_count: 'Joueurs',
  game_count: 'Matchs',
  previous_season_player_stat_count: 'Stats joueurs (N-1)',
  import_history_count: 'Historique des imports',
  prediction_count: 'Pronostics',
  login_lockout_count: 'Verrou anti-brute-force',
}

async function loadCounts() {
  errorMessage.value = ''
  try {
    counts.value = await apiFetch('/api/admin/table-counts')
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les compteurs.'
  }
}

async function runAudit() {
  errorMessage.value = ''
  isAuditing.value = true
  try {
    audit.value = await apiFetch('/api/admin/integrity-audit')
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Échec de l'audit."
  } finally {
    isAuditing.value = false
  }
}

onMounted(loadCounts)
</script>

<template>
  <section class="mx-auto max-w-2xl space-y-4 px-4 py-6">
    <h1 class="text-xl font-semibold text-accent-text">Base de données</h1>

    <p v-if="errorMessage" class="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">{{ errorMessage }}</p>

    <div v-if="counts" class="rounded-xl border border-border bg-surface p-4">
      <h2 class="mb-3 text-sm font-semibold text-text">Nombre de lignes par table</h2>
      <dl class="grid grid-cols-2 gap-2 text-sm">
        <template v-for="(label, key) in TABLE_LABELS" :key="key">
          <dt class="text-text-secondary">{{ label }}</dt>
          <dd class="text-right font-medium tabular-nums text-text">{{ counts[key] }}</dd>
        </template>
      </dl>
    </div>

    <div class="rounded-xl border border-border bg-surface p-4">
      <div class="mb-3 flex items-center justify-between">
        <h2 class="text-sm font-semibold text-text">Audit d'intégrité du calendrier</h2>
        <button
          type="button"
          class="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
          :disabled="isAuditing"
          @click="runAudit"
        >
          {{ isAuditing ? 'Audit en cours…' : "Auditer l'intégrité" }}
        </button>
      </div>

      <div v-if="audit" class="space-y-4 text-sm">
        <p class="text-text">
          {{ audit.total_games }} match(s) en base, {{ audit.team_game_counts.length }} équipe(s).
          Nombre de matchs le plus fréquent par équipe : <strong>{{ audit.mode_game_count }}</strong>.
          <span v-if="audit.mode_game_count !== 82" class="block text-xs text-text-secondary">
            (habituellement 82 sur une saison complète, ±1 pour la finale NBA Cup — un calendrier
            partiellement importé peut légitimement s'en écarter, ceci est informatif)
          </span>
          <span :class="audit.games_count_consistent ? 'text-success' : 'text-danger-text'">
            Cohérence interne (somme des matchs par équipe / 2 = total) :
            {{ audit.games_count_consistent ? 'OK' : 'ANOMALIE' }}.
          </span>
        </p>

        <div>
          <h3 class="mb-1 font-medium text-text">Matchs par équipe</h3>
          <p v-if="!audit.team_game_counts.some((t) => t.is_outlier)" class="text-success">
            RAS — aucune équipe ne s'écarte du nombre le plus fréquent de plus d'un match.
          </p>
          <ul v-else class="space-y-1">
            <li
              v-for="team in audit.team_game_counts.filter((t) => t.is_outlier)"
              :key="team.team_id"
              class="text-danger-text"
            >
              {{ team.team_name }} ({{ team.abbreviation }}) : {{ team.game_count }} match(s)
            </li>
          </ul>
        </div>

        <div>
          <h3 class="mb-1 font-medium text-text">Équipes NBA</h3>
          <p v-if="audit.missing_teams.length === 0 && audit.unexpected_teams.length === 0" class="text-success">
            RAS — les 30 équipes NBA sont présentes, aucune équipe inattendue.
          </p>
          <template v-else>
            <p v-if="audit.missing_teams.length" class="text-danger-text">
              Manquantes : {{ audit.missing_teams.join(', ') }}
            </p>
            <p v-if="audit.unexpected_teams.length" class="text-danger-text">
              Inattendues : {{ audit.unexpected_teams.join(', ') }}
            </p>
          </template>
        </div>

        <div>
          <h3 class="mb-1 font-medium text-text">Doublons (mêmes deux équipes, même date)</h3>
          <p v-if="audit.duplicate_games.length === 0" class="text-success">Aucun doublon détecté.</p>
          <ul v-else class="space-y-1">
            <li v-for="(dup, i) in audit.duplicate_games" :key="i" class="text-danger-text">
              {{ dup.team_a_abbreviation }} vs {{ dup.team_b_abbreviation }} le {{ dup.game_date }}
              ({{ dup.count }} lignes)
            </li>
          </ul>
        </div>

        <div>
          <h3 class="mb-1 font-medium text-text">Équipe sur deux matchs le même jour (adversaires différents)</h3>
          <p v-if="audit.same_day_conflicts.length === 0" class="text-success">Aucun conflit détecté.</p>
          <ul v-else class="space-y-1">
            <li v-for="(conflict, i) in audit.same_day_conflicts" :key="i" class="text-danger-text">
              {{ conflict.team_name }} le {{ conflict.game_date }} contre
              {{ conflict.opponent_abbreviations.join(' et ') }}
            </li>
          </ul>
        </div>
      </div>
    </div>
  </section>
</template>
