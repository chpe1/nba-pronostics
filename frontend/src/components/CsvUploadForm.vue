<script setup>
import { ref, watch, computed, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'
import RosterImportReview from '@/components/RosterImportReview.vue'
import {
  buildVerdictPayload,
  confirmLabel,
  detachmentBlockReasons,
  emptyVerdicts,
  unresolvedRows,
} from '@/utils/rosterVerdicts'

const emit = defineEmits(['imported'])

// Décision d'architecture n°35 (CLAUDE.md) : pas d'indicateur avant 200 ms, au moins 300 ms une fois
// affiché, et le libellé d'un bouton n'est jamais remplacé par un état d'attente. Date.now() (pas
// performance.now()) : même horloge que les minuteries simulées des tests.
const SLOW_MS = 200
const MIN_SPINNER_MS = 300
const showSpinner = ref(false)
const busyAction = ref(null) // 'preview' | 'confirm' | null

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

// Import d'EFFECTIF (Décision n°39) : verdicts sur les lignes sans correspondance et joueurs à
// détacher. Rien n'est jamais présélectionné : voir utils/rosterVerdicts.js.
const rosterVerdicts = ref({})
const selectedDetachIds = ref([])
const importReport = ref(null)

const fileInputRef = ref(null)
const selectedFile = ref(null)
const preview = ref(null)
const errorMessage = ref('')
const isLoading = ref(false)
const isRoster = computed(() => preview.value?.import_type === 'roster')
const rowsToDecide = computed(() => (isRoster.value ? preview.value.file_rows_without_match ?? [] : []))
const unresolvedCount = computed(() => unresolvedRows(rowsToDecide.value, rosterVerdicts.value).length)
const errorCount = computed(() => (isRoster.value ? preview.value.row_errors?.length ?? 0 : 0))
const detachBlocked = computed(
  () => detachmentBlockReasons({ unresolvedCount: unresolvedCount.value, errorCount: errorCount.value }).length > 0,
)
// Verdicts OBLIGATOIRES pour confirmer (règle du serveur, exposée par l'aperçu) : au moins une ligne sans
// correspondance ET au moins un joueur de la base absent du fichier. La garde qui compte est celle du
// serveur ; ce blocage évite seulement un aller-retour voué au refus.
const confirmBlocked = computed(() => isRoster.value && preview.value.verdicts_required === true && unresolvedCount.value > 0)
const confirmButtonLabel = computed(() => confirmLabel(isRoster.value ? selectedDetachIds.value.length : 0))
const seasonType = ref('current')
const season = ref('')
const currentSeason = ref('')
const previousSeason = ref('')
const teams = ref([])
const teamId = ref('')

async function loadTeams() {
  try {
    teams.value = await apiFetch('/api/teams')
  } catch {
    // Non bloquant : seul le roster par équipe en a besoin, l'erreur backend
    // (team_id manquant) guide de toute façon si ce champ reste vide.
  }
}

async function loadCurrentSeason() {
  try {
    const settings = await apiFetch('/api/settings')
    currentSeason.value = settings.current_season
    previousSeason.value = settings.previous_season
    season.value = currentSeason.value
  } catch {
    // Non bloquant : le champ saison reste éditable manuellement si le
    // réglage n'a pas pu être chargé.
  }
}

// Pré-remplit le champ saison depuis le réglage admin (jamais vide par
// défaut) -- toujours éditable pour un cas exceptionnel.
watch(seasonType, (value) => {
  season.value = value === 'previous' ? previousSeason.value : currentSeason.value
})

// L'aperçu est calculé pour un jeu de paramètres précis (saison, équipe) --
// le modifier après coup le rend caduc : un import confirmé sur un aperçu
// obsolète écrirait dans la mauvaise table ou sous la mauvaise équipe (voir
// discussion du chantier). Même geste que onFileChange pour un nouveau
// fichier -- on aligne les deux plutôt que d'inventer un second
// comportement. Réinitialisé même si la valeur revient à son état d'origine :
// un aperçu perdu pour rien coûte un clic, un aperçu qui ne correspond plus
// coûte un import dans la mauvaise table.
watch([seasonType, season, teamId], () => {
  preview.value = null
})

// Chaque nouvel aperçu repart de zéro : aucun verdict, aucune case cochée.
watch(preview, (value) => {
  rosterVerdicts.value = value?.import_type === 'roster' ? emptyVerdicts(value.file_rows_without_match ?? []) : {}
  selectedDetachIds.value = []
})

function onFileChange(event) {
  selectedFile.value = event.target.files[0] ?? null
  preview.value = null
  importReport.value = null
  errorMessage.value = ''
}

// Un <input type="file"> affiche le nom de fichier depuis son propre état
// DOM natif, pas depuis selectedFile -- il faut le réinitialiser
// explicitement via la ref, sinon le nom du fichier précédent reste affiché.
function resetFileInput() {
  selectedFile.value = null
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

async function upload(dryRun) {
  if (!selectedFile.value) return
  if (isLoading.value) return // garde du double clic (pas de `disabled` : il ferait clignoter le bouton, décision n°35)
  if (!dryRun && confirmBlocked.value) return
  if (seasonType.value === 'previous' && !season.value.trim()) {
    errorMessage.value = "Précisez la saison précédente (ex: \"2024-2025\")."
    return
  }

  isLoading.value = true
  busyAction.value = dryRun ? 'preview' : 'confirm'
  errorMessage.value = ''
  let shownAt = 0
  const slowTimer = setTimeout(() => {
    shownAt = Date.now()
    showSpinner.value = true
  }, SLOW_MS)
  // Termine l'attente en respectant la durée minimale d'affichage (décision n°35). Appelée AVANT de
  // démonter le bouton de confirmation (succès) -- sinon l'indicateur, qui vit dans ce bouton,
  // disparaîtrait avec lui sans avoir été affiché 300 ms -- et de nouveau dans `finally` (sans effet
  // quand elle a déjà eu lieu).
  async function settleBusy() {
    clearTimeout(slowTimer)
    if (showSpinner.value) {
      const remaining = MIN_SPINNER_MS - (Date.now() - shownAt)
      if (remaining > 0) await sleep(remaining)
    }
    showSpinner.value = false
  }
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    const params = new URLSearchParams({ dry_run: dryRun, season_type: seasonType.value })
    // Toujours envoyé si renseigné : requis pour un calendrier de matchs
    // (indépendamment du sélecteur courant/précédent, sans objet pour ce
    // type de fichier), optionnel sinon.
    if (season.value.trim()) {
      params.set('season', season.value.trim())
    }
    // Requis uniquement pour un roster Advanced d'une seule équipe (fichier
    // sans colonne Team) ; sans effet sinon.
    if (teamId.value) {
      params.set('team_id', teamId.value)
    }
    // Import d'effectif, confirmation : les verdicts (champ de formulaire) et la liste EXPLICITE des
    // identifiants à détacher (paramètre répété). Rien n'est jamais envoyé par défaut.
    if (!dryRun && isRoster.value) {
      const payload = buildVerdictPayload(rowsToDecide.value, rosterVerdicts.value)
      if (payload.length) {
        formData.append('verdicts', JSON.stringify(payload))
      }
      for (const id of selectedDetachIds.value) {
        params.append('detach_player_ids', id)
      }
    }
    const result = await apiFetch(`/api/imports/stats?${params.toString()}`, {
      method: 'POST',
      body: formData,
      isFormData: true,
    })

    if (dryRun) {
      preview.value = result
    } else {
      await settleBusy()
      preview.value = null
      importReport.value = result.import_history?.import_type === 'roster' ? result : null
      resetFileInput()
      emit('imported')
    }
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Échec de l'import."
    // Réinitialise aussi en cas de rejet d'une confirmation (pas d'un simple
    // aperçu) -- le fichier précédent n'a plus de raison de rester affiché.
    if (!dryRun) {
      resetFileInput()
    }
  } finally {
    await settleBusy()
    busyAction.value = null
    isLoading.value = false
  }
}

onMounted(() => {
  loadTeams()
  loadCurrentSeason()
})
</script>

<template>
  <div class="rounded-xl border border-border bg-surface p-4">
    <h2 class="mb-1 text-sm font-semibold text-text">Importer un fichier CSV (Basketball-Reference ou NBA.com)</h2>
    <p class="mb-3 text-xs text-text-secondary">
      Le type de fichier est <strong>détecté automatiquement</strong> à partir de ses colonnes.
      Dépose simplement le fichier tel quel.
    </p>

    <!-- Encadré qui EXPLIQUE (docs/design-v1.md §11.1) : rôle "encadré informatif" (§5.2/§5.3),
         jamais l'ambre -- ce texte n'avertit de rien, il décrit le déroulé en 2 étapes. -->
    <p class="mb-3 rounded-lg bg-surface-info px-3 py-2 text-xs text-text-secondary">
      Choisissez un fichier puis cliquez sur <strong>Aperçu</strong> — le type sera détecté
      automatiquement. Si tout est valide, cliquez sur <strong>Confirmer l'import</strong>.
    </p>

    <input
      ref="fileInputRef"
      type="file"
      accept=".csv"
      class="mb-3 block w-full text-sm text-text file:mr-3 file:min-h-11 file:cursor-pointer file:rounded-lg file:border-0 file:bg-text file:px-3 file:py-2 file:text-sm file:font-medium file:text-canvas hover:file:opacity-90"
      @change="onFileChange"
    />

    <fieldset class="mb-3 text-sm text-text">
      <legend class="mb-1 font-medium text-text">Saison (équipes / joueurs — sans objet pour la draft)</legend>
      <label class="mr-4 inline-flex min-h-11 items-center gap-1">
        <input v-model="seasonType" type="radio" value="current" />
        Saison courante<span v-if="currentSeason"> ({{ currentSeason }})</span>
      </label>
      <label class="inline-flex min-h-11 items-center gap-1">
        <input v-model="seasonType" type="radio" value="previous" />
        Saison précédente<span v-if="previousSeason"> ({{ previousSeason }})</span>
      </label>
      <input
        v-model="season"
        type="text"
        placeholder="ex: 2026-2027"
        class="mt-2 block w-40 rounded-lg border border-border px-2 py-1 text-sm"
      />
      <p class="mt-1 text-xs text-text-secondary">
        Pré-rempli depuis le réglage "Saison courante" (back-office Réglages), éditable si besoin.
        Requis pour un calendrier de matchs (le sélecteur ci-dessus est alors sans effet) ou pour "Saison précédente".
      </p>
    </fieldset>

    <fieldset class="mb-3 text-sm text-text">
      <legend class="mb-1 font-medium text-text">Équipe (roster par équipe uniquement)</legend>
      <select v-model="teamId" class="min-h-11 w-full max-w-xs rounded-lg border border-border px-2 py-1 text-sm">
        <option value="">—</option>
        <option v-for="team in teams" :key="team.id" :value="team.id">{{ team.name }}</option>
      </select>
      <p class="mt-1 text-xs text-text-secondary">
        Requis uniquement pour un roster Advanced d'une seule équipe (fichier sans colonne Team) ; sans effet sinon.
      </p>
    </fieldset>

    <div class="flex gap-2">
      <button
        type="button"
        class="flex min-h-11 items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm font-medium disabled:opacity-50"
        :disabled="!selectedFile"
        :aria-busy="busyAction === 'preview' && showSpinner"
        @click="upload(true)"
      >
        <span>Aperçu</span>
        <span class="flex h-4 w-4 shrink-0 items-center justify-center" aria-hidden="true">
          <svg
            v-if="busyAction === 'preview' && showSpinner"
            data-testid="import-spinner"
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
      <button
        v-if="preview"
        type="button"
        data-testid="confirm-button"
        class="flex min-h-11 items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
        :disabled="confirmBlocked"
        :aria-busy="busyAction === 'confirm' && showSpinner"
        @click="upload(false)"
      >
        <span>{{ confirmButtonLabel }}</span>
        <span class="flex h-4 w-4 shrink-0 items-center justify-center" aria-hidden="true">
          <svg
            v-if="busyAction === 'confirm' && showSpinner"
            data-testid="import-spinner"
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
    </div>

    <!-- Confirmation impossible : l'explication est VISIBLE à côté du bouton, pas seulement au survol. -->
    <p v-if="confirmBlocked" data-testid="confirm-blocked-notice" role="status" class="mt-2 text-sm text-text">
      <strong>Confirmation impossible :</strong> {{ unresolvedCount }} ligne(s) du fichier sans correspondance n'ont
      pas de verdict, alors que {{ preview.association_candidates.length }} joueur(s) de la base sont absents du
      fichier. Une de ces lignes pourrait être l'un d'eux, écrit autrement, et serait dupliquée. Tranchez chaque ligne
      ci-dessous.
    </p>
    <!-- N'existe que lorsque l'import est permis sans verdict (aucun joueur absent côté base) : une ligne sans
         correspondance ne peut alors être qu'une recrue. -->
    <p
      v-else-if="preview && isRoster && unresolvedCount > 0"
      data-testid="unresolved-import-warning"
      class="mt-2 text-sm text-text"
    >
      {{ unresolvedCount }} ligne(s) sans verdict seront importées comme des recrues (joueurs créés) si vous confirmez
      maintenant.
    </p>

    <p v-if="errorMessage" class="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">
      {{ errorMessage }}
    </p>

    <div v-if="importReport" data-testid="import-report" role="status" class="mt-4 space-y-2 rounded-lg border border-border p-3 text-sm text-text">
      <h3 class="font-semibold">Import d'effectif confirmé</h3>
      <p>
        {{ importReport.import_history.row_count }} ligne(s) importée(s) —
        <strong>{{ importReport.resolved_rows_count }}</strong> ligne(s) tranchée(s) :
        <strong>{{ importReport.recruit_count }}</strong> recrue(s),
        <strong>{{ importReport.association_count }}</strong> association(s).
      </p>
      <p v-if="importReport.recruit_names.length" class="text-text-secondary">
        Recrues : {{ importReport.recruit_names.join(', ') }}.
      </p>
      <ul v-if="importReport.associations.length" class="text-text-secondary">
        <li v-for="item in importReport.associations" :key="item.file_name">
          « {{ item.file_name }} » rattachée à {{ item.player_name }} (nom en base inchangé).
        </li>
      </ul>
      <p>
        <strong>{{ importReport.detached_count }}</strong> joueur(s) détaché(s) (agents libres)<template
          v-if="importReport.detached_names.length"
          >&nbsp;:</template
        ><template v-else>.</template>
      </p>
      <ul v-if="importReport.detached_names.length" class="columns-1 text-text-secondary sm:columns-2">
        <li v-for="name in importReport.detached_names" :key="name">{{ name }}</li>
      </ul>
    </div>

    <div v-if="preview" class="mt-4 text-sm">
      <!-- Encadré qui AVERTIT (docs/design-v1.md §11.1) : risque réel de mauvaise sélection avant
           un import qui écrase des données -- même traitement ambre que AdminTeamsView.vue. -->
      <p
        v-if="preview.resolved_team_name"
        class="mb-2 rounded-lg bg-warning/10 px-3 py-2 font-medium text-warning"
      >
        ⚠️ Équipe résolue pour cet import : <strong>{{ preview.resolved_team_name }} ({{ preview.resolved_team_abbreviation }})</strong>
        — vérifie que c'est la bonne avant de confirmer (le fichier ne contient aucune info d'équipe à croiser).
      </p>

      <p class="mb-2 text-text">
        Type détecté : <strong>{{ preview.import_type }}</strong>
        <span v-if="preview.season"> (saison {{ preview.season }})</span> —
        {{ preview.row_count }} ligne(s) valide(s), {{ preview.error_count }} erreur(s).
      </p>

      <div
        v-if="preview.errors.length && preview.import_type !== 'roster'"
        class="mb-2 rounded-lg bg-warning/10 px-3 py-2 text-warning"
      >
        <p v-for="err in preview.errors" :key="err.row">Ligne {{ err.row }} : {{ err.message }}</p>
      </div>

      <!-- Récapitulatif ROSTER (effectif complet) : 5 sections dans l'ordre
           du plan du chantier. Chaque section au-delà d'un simple compte est
           repliée par défaut (<details>, jamais de pagination) : la liste
           complète (jusqu'à une centaine de noms) reste dans le DOM, juste
           masquée tant qu'on ne l'ouvre pas -- évite le mur de texte sans
           découper les données en pages. -->
      <div v-if="preview.import_type === 'roster'" class="space-y-3">
        <!-- Dans l'ORDRE DES DÉCISIONS : lignes à trancher, lignes en erreur, joueurs à détacher. -->
        <RosterImportReview
          v-model:verdicts="rosterVerdicts"
          v-model:selected-ids="selectedDetachIds"
          :preview="preview"
        />

        <p class="rounded-lg bg-surface-info px-3 py-2 text-text-secondary">
          <strong>{{ preview.matched_count }}</strong> joueur(s) rapproché(s) d'une ligne de statistiques N-1.
        </p>

        <details v-if="preview.unmatched.length" class="rounded-lg border border-border">
          <summary class="flex min-h-11 cursor-pointer items-center px-3 py-2 font-medium text-text">
            {{ preview.unmatched.length }} échec(s) de rapprochement
          </summary>
          <ul class="divide-y divide-border px-3 pb-2 text-text-secondary">
            <li v-for="item in preview.unmatched" :key="item.name" class="py-1.5">
              {{ item.name }}
              <span v-if="item.closest_match">
                — le plus proche en base : {{ item.closest_match }} (distance {{ item.distance }})
              </span>
              <span v-else>— aucune suggestion trouvée</span>
            </li>
          </ul>
        </details>
        <p v-else class="text-text-secondary">Aucun échec de rapprochement.</p>

        <details v-if="preview.moved.length" class="rounded-lg border border-border">
          <summary class="flex min-h-11 cursor-pointer items-center px-3 py-2 font-medium text-text">
            {{ preview.moved.length }} ligne(s) déplacée(s) d'une équipe à l'autre
          </summary>
          <ul class="divide-y divide-border px-3 pb-2 text-text-secondary">
            <li v-for="item in preview.moved" :key="item.name" class="py-1.5">
              {{ item.name }} : {{ item.from_team }} → {{ item.to_team }}
            </li>
          </ul>
        </details>
        <p v-else class="text-text-secondary">Aucune ligne déplacée.</p>

        <details v-if="preview.no_prior_data.length" class="rounded-lg border border-border">
          <summary class="flex min-h-11 cursor-pointer items-center px-3 py-2 font-medium text-text">
            {{ preview.no_prior_data.length }} joueur(s) sans ligne N-1 ni draft_pick connu
          </summary>
          <ul class="divide-y divide-border px-3 pb-2 text-text-secondary">
            <li v-for="name in preview.no_prior_data" :key="name" class="py-1.5">{{ name }}</li>
          </ul>
        </details>
        <p v-else class="text-text-secondary">Aucun joueur à signaler.</p>
      </div>

      <div v-else-if="preview.sample_rows && preview.sample_rows.length" class="overflow-x-auto">
        <table class="w-full border-collapse text-left text-xs">
          <thead>
            <tr>
              <th v-for="key in Object.keys(preview.sample_rows[0])" :key="key" class="border-b p-1 font-medium">
                {{ key }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in preview.sample_rows" :key="i">
              <td v-for="key in Object.keys(row)" :key="key" class="border-b p-1">{{ row[key] }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
