<script setup>
import { ref, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'

// Valeur du filtre : '' (toutes les équipes), FREE_AGENT_FILTER (agents libres : joueurs sans équipe,
// Décision d'architecture n°39) ou l'identifiant d'une équipe.
const FREE_AGENT_FILTER = 'free-agent'
const teams = ref([])
const filterValue = ref('')
let lastConfirmedFilter = ''
const infoMessage = ref('')
const players = ref([])
const forms = ref({})
const isLoading = ref(false)
const errorMessage = ref('')
// Troisième état, distinct des deux autres : des données, une absence
// VÉRIFIÉE, un échec (docs/design-v1.md §12). Sans lui, un échec de
// chargement laissait à l'écran la liste du contexte précédent -- sous le
// nouveau contexte sélectionné, donc en affirmant qu'elle lui appartenait.
const loadFailed = ref(false)
const savingId = ref(null)
const savedId = ref(null)
const deletingId = ref(null)

const newPlayer = ref({ name: '', team_id: '', draft_pick: '', per: '', mpg: '' })
const isCreating = ref(false)
const createMessage = ref('')

function toNumberOrNull(value) {
  return value === '' || value === null || value === undefined ? null : Number(value)
}

function buildForm(player) {
  return {
    name: player.name,
    // Un agent libre n'a pas d'équipe : '' (l'option « agent libre » du sélecteur, non choisissable).
    team_id: player.team_id ?? '',
    draft_pick: player.draft_pick,
    per: player.per,
    mpg: player.mpg,
  }
}

async function loadTeams() {
  try {
    teams.value = await apiFetch('/api/teams')
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les équipes.'
  }
}

function playersPath() {
  if (filterValue.value === FREE_AGENT_FILTER) return '/api/players?free_agent=true'
  return filterValue.value ? `/api/players?team_id=${filterValue.value}` : '/api/players'
}

function matchesFilter(player) {
  if (filterValue.value === '') return true
  if (filterValue.value === FREE_AGENT_FILTER) return player.team_id === null
  return String(player.team_id) === String(filterValue.value)
}

async function loadPlayers() {
  isLoading.value = true
  errorMessage.value = ''
  infoMessage.value = ''
  loadFailed.value = false
  try {
    const path = playersPath()
    players.value = await apiFetch(path)
    forms.value = Object.fromEntries(players.value.map((p) => [p.id, buildForm(p)]))
  } catch (error) {
    // Vidée ICI : sans cela les joueurs de l'équipe précédente restaient
    // listés sous l'équipe nouvellement sélectionnée.
    players.value = []
    forms.value = {}
    loadFailed.value = true
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les joueurs.'
  } finally {
    isLoading.value = false
  }
}

// Une fiche est modifiée si sa saisie diffère de la dernière valeur connue du serveur -- même comparaison
// normalisée que l'enregistrement (un champ numérique touché puis remis à sa valeur d'origine ne compte pas).
function isDirty(player) {
  const form = forms.value[player.id]
  if (!form) return false
  return (
    form.name !== player.name ||
    String(form.team_id ?? '') !== String(player.team_id ?? '') ||
    toNumberOrNull(form.draft_pick) !== player.draft_pick ||
    toNumberOrNull(form.per) !== player.per ||
    toNumberOrNull(form.mpg) !== player.mpg
  )
}

// Changer de filtre recharge la liste et PERD les saisies non enregistrées : avertir avant, jamais après.
function confirmDiscardUnsavedEdits() {
  const dirtyCount = players.value.filter((p) => isDirty(p)).length
  if (dirtyCount === 0) return true
  const message =
    dirtyCount === 1
      ? 'Une fiche a une saisie non enregistrée, qui sera perdue.\n\nContinuer ?'
      : `${dirtyCount} fiches ont une saisie non enregistrée, qui sera perdue.\n\nContinuer ?`
  return window.confirm(message)
}

// PAS de v-model sur ce <select> (Décision d'architecture n°31, limitation n°23) : sur un <select>,
// v-model et @change partagent le MÊME événement natif `change` et se disputent la valeur. Sur annulation,
// l'option AFFICHÉE doit revenir à la dernière valeur confirmée -- affectation DOM explicite, car le
// navigateur a déjà commis le choix avant que `change` ne se déclenche.
function onFilterChange(event) {
  const newValue = event.target.value
  if (!confirmDiscardUnsavedEdits()) {
    event.target.value = lastConfirmedFilter
    return
  }
  filterValue.value = newValue
  lastConfirmedFilter = newValue
  loadPlayers()
}

async function save(player) {
  const form = forms.value[player.id]
  errorMessage.value = ''
  savedId.value = null
  savingId.value = player.id
  try {
    const updated = await apiFetch(`/api/players/${player.id}`, {
      method: 'PATCH',
      body: {
        name: form.name,
        // Un agent libre dont l'équipe n'est pas choisie : team_id n'est PAS envoyé (jamais 0, jamais null --
        // détacher est impossible depuis cet écran, Décision n°39) ; seul un vrai choix replace le joueur.
        ...(form.team_id === '' || form.team_id === null ? {} : { team_id: Number(form.team_id) }),
        draft_pick: toNumberOrNull(form.draft_pick),
        per: toNumberOrNull(form.per),
        mpg: toNumberOrNull(form.mpg),
      },
    })
    if (matchesFilter(updated)) {
      const idx = players.value.findIndex((p) => p.id === player.id)
      players.value[idx] = updated
      forms.value[player.id] = buildForm(updated)
      savedId.value = player.id
    } else {
      // Replacé dans une équipe depuis la liste des agents libres (ou changé d'équipe sous un filtre
      // d'équipe) : la fiche n'appartient plus à cette liste -- on le dit au lieu de la laisser mentir.
      players.value = players.value.filter((p) => p.id !== player.id)
      delete forms.value[player.id]
      infoMessage.value = `${updated.name} est maintenant à ${updated.team_name} : il n'apparaît plus dans cette liste.`
    }
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Échec de l'enregistrement."
  } finally {
    savingId.value = null
  }
}

async function deletePlayer(player) {
  const confirmed = window.confirm(
    `Supprimer définitivement ${player.name} (${player.team_abbreviation ?? 'agent libre'}) ? Cette action est irréversible.`
  )
  if (!confirmed) return

  errorMessage.value = ''
  deletingId.value = player.id
  try {
    await apiFetch(`/api/players/${player.id}`, { method: 'DELETE' })
    players.value = players.value.filter((p) => p.id !== player.id)
    delete forms.value[player.id]
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Échec de la suppression.'
  } finally {
    deletingId.value = null
  }
}

async function createPlayer() {
  errorMessage.value = ''
  createMessage.value = ''
  if (!newPlayer.value.name || !newPlayer.value.team_id) {
    errorMessage.value = 'Nom et équipe sont obligatoires.'
    return
  }
  isCreating.value = true
  try {
    const created = await apiFetch('/api/players', {
      method: 'POST',
      body: {
        name: newPlayer.value.name,
        team_id: Number(newPlayer.value.team_id),
        draft_pick: toNumberOrNull(newPlayer.value.draft_pick),
        per: toNumberOrNull(newPlayer.value.per),
        mpg: toNumberOrNull(newPlayer.value.mpg),
      },
    })
    createMessage.value = 'Joueur enregistré.'
    newPlayer.value = { name: '', team_id: newPlayer.value.team_id, draft_pick: '', per: '', mpg: '' }
    // (jamais pour le filtre « agents libres » : un joueur qu'on vient de créer a une équipe)
    if (filterValue.value === '' || filterValue.value === String(created.team_id)) {
      await loadPlayers()
    }
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Échec de l'enregistrement."
  } finally {
    isCreating.value = false
  }
}

onMounted(async () => {
  await loadTeams()
  await loadPlayers()
})
</script>

<template>
  <section class="mx-auto max-w-2xl space-y-4 px-4 py-6">
    <h1 class="text-xl font-semibold text-text">Joueurs</h1>
    <p class="text-sm text-text-secondary">
      Ajouter ou corriger un joueur à la main (rookie drafté, correction ponctuelle). Un
      PER/MPG saisi ici est un simple placeholder : le prochain import CSV Advanced du
      même joueur l'écrase normalement, sans protection particulière.
    </p>

    <!-- Erreur qui ACCOMPAGNE des données encore valables (échec d'un
         enregistrement, d'une suppression) : elle se pose au-dessus. Un échec
         de CHARGEMENT, lui, prend la place de la liste, plus bas (§12). -->
    <p v-if="errorMessage && !loadFailed" class="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">{{ errorMessage }}</p>

    <div class="space-y-3 rounded-xl border border-border bg-surface p-4">
      <h2 class="text-sm font-semibold text-text">Ajouter un joueur</h2>
      <div class="grid grid-cols-2 gap-3">
        <div class="col-span-2">
          <label class="mb-1 block text-xs font-medium text-text">Nom complet (ex : LeBron James)</label>
          <input v-model="newPlayer.name" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div class="col-span-2">
          <label class="mb-1 block text-xs font-medium text-text">Équipe</label>
          <select v-model="newPlayer.team_id" class="min-h-11 w-full rounded-lg border border-border px-3 py-2 text-sm">
            <option value="" disabled>Sélectionner une équipe</option>
            <option v-for="team in teams" :key="team.id" :value="team.id">{{ team.name }}</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Pick draft</label>
          <input v-model="newPlayer.draft_pick" type="number" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">PER</label>
          <input v-model="newPlayer.per" type="number" step="0.1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">MPG</label>
          <input v-model="newPlayer.mpg" type="number" step="0.1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
      </div>
      <button
        type="button"
        class="min-h-11 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
        :disabled="isCreating"
        @click="createPlayer"
      >
        {{ isCreating ? 'Enregistrement…' : 'Ajouter / mettre à jour' }}
      </button>
      <p v-if="createMessage" class="text-xs text-success">{{ createMessage }}</p>
    </div>

    <div class="flex items-center gap-2">
      <label for="team-filter" class="text-sm font-medium text-text">Équipe</label>
      <select
        id="team-filter"
        :value="filterValue"
        class="min-h-11 rounded-lg border border-border px-3 py-2 text-sm"
        @change="onFilterChange"
      >
        <option value="">Toutes les équipes</option>
        <option :value="FREE_AGENT_FILTER">Agents libres</option>
        <option v-for="team in teams" :key="team.id" :value="team.id">{{ team.name }}</option>
      </select>
    </div>

    <p v-if="infoMessage" role="status" class="rounded-lg bg-surface-info px-3 py-2 text-sm text-text-secondary">
      {{ infoMessage }}
    </p>

    <p v-if="isLoading" class="text-sm text-text-secondary">Chargement…</p>
    <!-- L'échec prend la PLACE des données, il ne se superpose pas à elles
         (§12) : ni liste, ni message de vide. Placé avant la branche du vide
         dans la chaîne, il l'exclut mécaniquement -- les deux s'affichaient
         ensemble jusqu'ici, et l'une des deux était fausse. -->
    <div v-else-if="loadFailed" role="alert" class="rounded-lg bg-danger/10 p-3">
      <p class="text-sm text-danger-text">{{ errorMessage }}</p>
      <!-- Relance le contexte COURANT, sans rien changer à la sélection. -->
      <button
        type="button"
        class="mt-3 min-h-11 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
        :disabled="isLoading"
        @click="loadPlayers"
      >
        Réessayer
      </button>
    </div>

    <p v-else-if="players.length === 0" class="text-sm text-text-secondary">Aucun joueur.</p>

    <div
      v-for="player in players"
      :key="player.id"
      data-testid="player-card"
      class="space-y-3 rounded-xl border border-border bg-surface p-4"
    >
      <div class="text-sm font-medium text-text">
        {{ player.team_abbreviation ?? 'agent libre' }} — {{ player.injury_status }}<span v-if="!player.is_active"> — inactif</span>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div class="col-span-2">
          <label class="mb-1 block text-xs font-medium text-text">Nom complet (ex : LeBron James)</label>
          <input v-model="forms[player.id].name" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div class="col-span-2">
          <label class="mb-1 block text-xs font-medium text-text">Équipe</label>
          <select v-model="forms[player.id].team_id" class="min-h-11 w-full rounded-lg border border-border px-3 py-2 text-sm">
            <!-- État COURANT d'un agent libre : affiché mais NON choisissable (disabled). On peut replacer un
                 agent libre dans une équipe, jamais détacher depuis cet écran (Décision n°39). -->
            <option v-if="player.team_id === null" value="" disabled>— Agent libre —</option>
            <option v-for="team in teams" :key="team.id" :value="team.id">{{ team.name }}</option>
          </select>
          <!-- La consigne vit ICI, sous le champ, où elle passe à la ligne : une option de <select> est
               coupée en plein mot sur petit écran. -->
          <p v-if="player.team_id === null" data-testid="free-agent-help" class="mt-1 text-xs text-text-secondary">
            Aucune équipe : choisissez-en une pour replacer ce joueur. On ne peut pas détacher un joueur depuis
            cet écran (seulement via l'aperçu d'import d'effectif).
          </p>
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Pick draft</label>
          <input v-model="forms[player.id].draft_pick" type="number" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">PER</label>
          <input v-model="forms[player.id].per" type="number" step="0.1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">MPG</label>
          <input v-model="forms[player.id].mpg" type="number" step="0.1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
      </div>

      <div class="flex gap-2">
        <button
          type="button"
          class="min-h-11 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
          :disabled="savingId === player.id || deletingId === player.id"
          @click="save(player)"
        >
          {{ savingId === player.id ? 'Enregistrement…' : 'Enregistrer' }}
        </button>
        <button
          type="button"
          class="min-h-11 rounded-lg border border-danger text-sm font-medium text-danger-text px-3 py-2 disabled:opacity-50"
          :disabled="savingId === player.id || deletingId === player.id"
          @click="deletePlayer(player)"
        >
          {{ deletingId === player.id ? 'Suppression…' : 'Supprimer' }}
        </button>
      </div>
      <p v-if="savedId === player.id" class="text-xs text-success">Enregistré.</p>
    </div>
  </section>
</template>
