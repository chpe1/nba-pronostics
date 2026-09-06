<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'

const stats = ref([])
const forms = ref({})
const filterSeason = ref('')
const filterPlayerName = ref('')

// Pagination (limitation n°14). `page` est la seule valeur que le client
// possède avant toute réponse ; `total`/`size` viennent du serveur et
// pilotent l'affichage du pager -- voir `totalPages` plus bas, écrit pour
// rester correct tant que `pageSize` est encore inconnu (avant la première
// réponse réussie), par construction et non par accident de calcul sur NaN.
const page = ref(1)
const total = ref(0)
const pageSize = ref(null)

const isLoading = ref(false)
const errorMessage = ref('')
// Troisième état, distinct des deux autres : des données, une absence
// VÉRIFIÉE, un échec (docs/design-v1.md §12). Sans lui, un échec de
// chargement laissait à l'écran la liste du contexte précédent -- sous le
// nouveau contexte sélectionné, donc en affirmant qu'elle lui appartenait.
const loadFailed = ref(false)
const savingId = ref(null)
const savedId = ref(null)
// Confirmation au niveau de l'ÉCRAN, distincte de `savedId` (au niveau de
// la LIGNE) : couvre le cas où un enregistrement réussi fait sortir la
// ligne de la page rechargée (voir `save()`) -- sans elle, un succès réel
// ne montrerait plus rien, indiscernable d'un échec silencieux.
const savedBanner = ref('')
// Un seul mécanisme pour les TROIS chemins d'écriture (save/createStat/
// deleteStat) : ce que voit l'admin quand l'écriture elle-même a réussi
// mais que le rechargement qui la suit échoue. Sans lui, l'écran bascule
// sur le bloc `loadFailed` sans jamais dire que le geste a fonctionné --
// l'admin conclurait à tort que son enregistrement/sa création/sa
// suppression a échoué. Remis à '' au début de chaque écriture et à
// chaque chargement réussi (`loadStats`/`reloadCurrentPageKeepingEdits`) :
// ne doit jamais survivre à l'écran auquel il s'applique, en particulier
// un « Réessayer » réussi le fait disparaître.
const writeSucceededMessage = ref('')
const deletingId = ref(null)

const newStat = ref({ season: '', player_name: '', team_abbreviation: '', per: '', mpg: '' })
const isCreating = ref(false)
const createMessage = ref('')

// Dernières valeurs de filtre CONFIRMÉES (une saisie non enregistrée n'a pas
// été perdue sous ce filtre-là) -- permettent de restaurer l'affichage des
// champs si l'admin annule un changement de filtre à cause d'une saisie non
// enregistrée (voir `onFilterChange`). Volontairement de simples variables
// fermées, pas des refs : jamais lues par le template.
let lastConfirmedSeason = ''
let lastConfirmedPlayerName = ''

function toNumberOrNull(value) {
  return value === '' || value === null || value === undefined ? null : Number(value)
}

function buildForm(stat) {
  return {
    season: stat.season,
    player_name: stat.player_name,
    team_abbreviation: stat.team_abbreviation,
    per: stat.per,
    mpg: stat.mpg,
  }
}

// Un formulaire est modifié si sa valeur diffère de la dernière valeur
// connue du serveur pour cette ligne -- comparaison normalisée par
// `toNumberOrNull`, le même chemin que l'enregistrement (§12 : sans cette
// normalisation, un champ numérique touché puis remis à sa valeur d'origine
// serait déclaré modifié à tort, un faux positif qui userait la confirmation).
function isDirty(statId) {
  const form = forms.value[statId]
  const stat = stats.value.find((s) => s.id === statId)
  if (!form || !stat) return false
  return (
    form.season !== stat.season ||
    form.player_name !== stat.player_name ||
    form.team_abbreviation !== stat.team_abbreviation ||
    toNumberOrNull(form.per) !== stat.per ||
    toNumberOrNull(form.mpg) !== stat.mpg
  )
}

// Garde commune à tout ce qui change de PAGE ou de FILTRE (Précédent,
// Suivant, « Revenir à la première page », les deux champs de filtre) :
// une saisie non enregistrée survit à un rechargement de la MÊME page
// (voir `reloadCurrentPageKeepingEdits`), mais se perd en changeant de
// page ou de filtre -- avertir avant, jamais après.
function confirmDiscardUnsavedEdits() {
  const dirtyCount = stats.value.filter((s) => isDirty(s.id)).length
  if (dirtyCount === 0) return true
  const message =
    dirtyCount === 1
      ? 'Une ligne a une saisie non enregistrée, qui sera perdue.\n\nContinuer ?'
      : `${dirtyCount} lignes ont une saisie non enregistrée, qui sera perdue.\n\nContinuer ?`
  return window.confirm(message)
}

const totalPages = computed(() => {
  if (!pageSize.value) return 0
  return Math.ceil(total.value / pageSize.value)
})
// Masqué si une seule page (ou aucune) : un pager dont l'action serait
// toujours un no-op n'a rien à montrer -- même principe que la réserve de
// pastilles sur le maximum réellement affiché (pastilles.js) ou le
// pointillé de DateStrip. Se masque de lui-même sur un échec de chargement
// ou sur `total === 0`, `total` étant remis à 0 dans les deux cas.
const showPager = computed(() => totalPages.value > 1)

async function loadDefaultSeason() {
  try {
    const settings = await apiFetch('/api/settings')
    newStat.value.season = settings.previous_season
    filterSeason.value = settings.previous_season
    lastConfirmedSeason = settings.previous_season
  } catch {
    // Non bloquant : les champs saison restent éditables manuellement.
  }
}

async function loadStats() {
  isLoading.value = true
  errorMessage.value = ''
  loadFailed.value = false
  try {
    const params = new URLSearchParams()
    if (filterSeason.value.trim()) params.set('season', filterSeason.value.trim())
    if (filterPlayerName.value.trim()) params.set('player_name', filterPlayerName.value.trim())
    params.set('page', String(page.value))
    const response = await apiFetch(`/api/previous-season-stats?${params.toString()}`)
    stats.value = response.items
    total.value = response.total
    pageSize.value = response.size
    forms.value = Object.fromEntries(stats.value.map((s) => [s.id, buildForm(s)]))
    // Un chargement réussi -- notamment un « Réessayer » -- referme la
    // fenêtre où ce message avait un sens : il ne doit jamais survivre à
    // l'écran auquel il s'applique.
    writeSucceededMessage.value = ''
  } catch (error) {
    // Vidée ICI : sans cela les lignes de la page/du filtre précédents
    // restaient affichées sous le nouveau contexte. `total` à 0 avec elle :
    // sans ça le pager resterait visible avec un compte de pages périmé
    // pendant l'affichage du bloc d'erreur.
    stats.value = []
    forms.value = {}
    total.value = 0
    loadFailed.value = true
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les statistiques.'
  } finally {
    isLoading.value = false
  }
}

// Recharge la page COURANTE (jamais un changement de page/filtre) depuis le
// serveur, en préservant les saisies non enregistrées des lignes qui
// restent affichées -- utilisée après save()/deleteStat()/createStat(),
// jamais après un changement de contexte (qui passe par loadStats() via
// goToPage()/onFilterChange(), lesquels ont déjà obtenu confirmation de la
// perte). Diverge ici du patch local d'AdminGamesView.save() : sous
// pagination, une page porte davantage de lignes, et effacer les éditions
// en cours d'un enregistrement voisin serait une perte silencieuse alors
// que le reste de l'écran avertit désormais sur toute perte de saisie.
// N'écrit son propre message d'erreur que sur échec, jamais "Échec de
// l'enregistrement" pour un PATCH/POST/DELETE qui a en réalité réussi.
async function reloadCurrentPageKeepingEdits() {
  errorMessage.value = ''
  loadFailed.value = false
  try {
    const params = new URLSearchParams()
    if (filterSeason.value.trim()) params.set('season', filterSeason.value.trim())
    if (filterPlayerName.value.trim()) params.set('player_name', filterPlayerName.value.trim())
    params.set('page', String(page.value))
    const response = await apiFetch(`/api/previous-season-stats?${params.toString()}`)
    const previousForms = forms.value
    stats.value = response.items
    total.value = response.total
    pageSize.value = response.size
    forms.value = Object.fromEntries(
      stats.value.map((s) => {
        const fresh = buildForm(s)
        const previous = previousForms[s.id]
        const wasDirty =
          previous &&
          (previous.season !== fresh.season ||
            previous.player_name !== fresh.player_name ||
            previous.team_abbreviation !== fresh.team_abbreviation ||
            toNumberOrNull(previous.per) !== fresh.per ||
            toNumberOrNull(previous.mpg) !== fresh.mpg)
        return [s.id, wasDirty ? previous : fresh]
      })
    )
    writeSucceededMessage.value = ''
    return true
  } catch (error) {
    stats.value = []
    forms.value = {}
    total.value = 0
    loadFailed.value = true
    errorMessage.value = error instanceof ApiError ? error.message : 'Impossible de charger les statistiques.'
    return false
  }
}

function goToPage(target) {
  if (!confirmDiscardUnsavedEdits()) return
  page.value = target
  loadStats()
}

function onFilterChange() {
  if (!confirmDiscardUnsavedEdits()) {
    // Annulé : les deux champs reviennent à leur dernière valeur confirmée
    // -- v-model a déjà appliqué la saisie avant que @change ne se déclenche,
    // « annuler » doit donc effacer ce changement, pas seulement renoncer au
    // rechargement (sans quoi le champ affiché divergerait des données
    // réellement chargées).
    filterSeason.value = lastConfirmedSeason
    filterPlayerName.value = lastConfirmedPlayerName
    return
  }
  lastConfirmedSeason = filterSeason.value
  lastConfirmedPlayerName = filterPlayerName.value
  page.value = 1
  loadStats()
}

async function save(stat) {
  const form = forms.value[stat.id]
  errorMessage.value = ''
  savedId.value = null
  savedBanner.value = ''
  writeSucceededMessage.value = ''
  savingId.value = stat.id
  try {
    await apiFetch(`/api/previous-season-stats/${stat.id}`, {
      method: 'PATCH',
      body: {
        season: form.season,
        player_name: form.player_name,
        team_abbreviation: form.team_abbreviation,
        per: toNumberOrNull(form.per),
        mpg: toNumberOrNull(form.mpg),
      },
    })
    const succeeded = await reloadCurrentPageKeepingEdits()
    if (succeeded) {
      if (stats.value.some((s) => s.id === stat.id)) {
        savedId.value = stat.id
      } else {
        // La ligne a quitté le filtre ou la page affichés (ex : saison
        // changée) -- la confirmation par ligne n'a plus de ligne où se
        // poser, elle passe au niveau de l'écran pour ne pas rester muette.
        savedBanner.value = 'Ligne enregistrée -- elle ne correspond plus aux filtres ou à la page affichés.'
      }
    } else {
      // Le PATCH a réussi, seul le rechargement qui le suit a échoué :
      // l'écran bascule sur `loadFailed`, qui vide la liste (correct, voir
      // reloadCurrentPageKeepingEdits) -- mais sans ce message, rien ne dit
      // que l'enregistrement, lui, a fonctionné. Un message générique
      // serait faux pour createStat()/deleteStat() : celui-ci nomme
      // l'opération.
      writeSucceededMessage.value = 'La modification a été enregistrée ; seul le rafraîchissement de la liste a échoué.'
    }
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Échec de l'enregistrement."
  } finally {
    savingId.value = null
  }
}

async function createStat() {
  errorMessage.value = ''
  createMessage.value = ''
  writeSucceededMessage.value = ''
  if (!newStat.value.season || !newStat.value.player_name || !newStat.value.team_abbreviation) {
    errorMessage.value = 'Saison, nom du joueur et abréviation d\'équipe sont obligatoires.'
    return
  }
  isCreating.value = true
  try {
    await apiFetch('/api/previous-season-stats', {
      method: 'POST',
      body: {
        season: newStat.value.season,
        player_name: newStat.value.player_name,
        team_abbreviation: newStat.value.team_abbreviation,
        per: toNumberOrNull(newStat.value.per),
        mpg: toNumberOrNull(newStat.value.mpg),
      },
    })
    createMessage.value = 'Ligne créée.'
    newStat.value = { ...newStat.value, player_name: '', team_abbreviation: '', per: '', mpg: '' }
    // Compromis assumé (pagination uniquement, pas de saut vers la page
    // d'atterrissage) : recharge la page COURANTE, où la nouvelle ligne
    // n'apparaît que si elle y trie. `createMessage` reste le seul signal
    // de succès dans le cas contraire -- sauter vers sa page déplacerait la
    // vue sans que l'admin l'ait demandé.
    const succeeded = await reloadCurrentPageKeepingEdits()
    if (!succeeded) {
      // Le POST a réussi (createMessage le dit, dans la carte « Ajouter »),
      // mais ce message-ci accompagne spécifiquement le bloc `loadFailed`
      // qui vient de remplacer la liste plus bas -- sans lui, cette partie
      // de l'écran ne dirait rien du succès de la création.
      writeSucceededMessage.value = 'La ligne a été créée ; seul le rafraîchissement de la liste a échoué.'
    }
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Échec de l'enregistrement."
  } finally {
    isCreating.value = false
  }
}

async function deleteStat(stat) {
  // Élément dessiné par le système (§12) : son rendu réel (position,
  // largeur, boutons) échappe à toute mesure automatisée.
  const confirmed = window.confirm(
    `Supprimer définitivement la ligne ${stat.player_name} (${stat.season}, ${stat.team_abbreviation}) ? ` +
      "N'affecte que les futurs recalculs (le joueur retombe sur le cas \"pas de fallback disponible\") -- " +
      'les pronostics déjà calculés ne changent pas. Cette action est irréversible.'
  )
  if (!confirmed) return

  errorMessage.value = ''
  writeSucceededMessage.value = ''
  deletingId.value = stat.id
  try {
    await apiFetch(`/api/previous-season-stats/${stat.id}`, { method: 'DELETE' })
    // La suppression elle-même a réussi à ce stade -- tout ce qui suit ne
    // peut plus la remettre en cause, seulement échouer à en RENDRE COMPTE.
    // Cas le plus grave des trois chemins (l'admin croirait la ligne encore
    // là) : chaque échec de rechargement, y compris celui du repli, pose ce
    // message plutôt que de laisser `loadFailed` parler seul.
    let succeeded = await reloadCurrentPageKeepingEdits()
    // Repli d'une page si la suppression a vidé la DERNIÈRE page affichée --
    // au plus une requête de plus : une suppression ne peut invalider que la
    // page courante, jamais en cascade.
    if (succeeded && stats.value.length === 0 && page.value > 1) {
      page.value -= 1
      succeeded = await reloadCurrentPageKeepingEdits()
    }
    if (!succeeded) {
      writeSucceededMessage.value = 'La ligne a été supprimée ; seul le rafraîchissement de la liste a échoué.'
    }
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Échec de la suppression.'
  } finally {
    deletingId.value = null
  }
}

onMounted(async () => {
  await loadDefaultSeason()
  await loadStats()
})
</script>

<template>
  <section class="mx-auto max-w-2xl space-y-4 px-4 py-6">
    <h1 class="text-xl font-semibold text-text">Statistiques joueurs (saison précédente)</h1>
    <p class="text-sm text-text-secondary">
      Corriger une ligne à la main (ex : une résolution d'équipe erronée sur un cas d'encodage
      particulier) sans devoir réimporter tout le fichier ligue entière. Sert à la détection des
      transferts et au garde-fou petit échantillon.
    </p>

    <!-- Erreur qui ACCOMPAGNE des données encore valables (échec d'un
         enregistrement, d'une suppression) : elle se pose au-dessus. Un échec
         de CHARGEMENT, lui, prend la place de la liste, plus bas (§12). -->
    <p v-if="errorMessage && !loadFailed" class="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">{{ errorMessage }}</p>
    <p v-if="savedBanner" class="text-sm text-success">{{ savedBanner }}</p>
    <!-- AU-DESSUS du bloc `loadFailed` plus bas, sans le remplacer : les
         deux informations sont vraies en même temps (l'écriture a réussi,
         la liste n'a pas pu être rechargée). Gardé hors de la chaîne à
         cinq branches -- v-else-if l'exigerait consécutif au v-if
         précédent, alors qu'ici les deux coexistent à l'écran. -->
    <p v-if="writeSucceededMessage && loadFailed" class="text-sm text-success">{{ writeSucceededMessage }}</p>

    <div class="space-y-3 rounded-xl border border-border bg-surface p-4">
      <h2 class="text-sm font-semibold text-text">Ajouter une ligne</h2>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Saison (ex : 2024-2025)</label>
          <input v-model="newStat.season" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">Équipe (abréviation)</label>
          <input v-model="newStat.team_abbreviation" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div class="col-span-2">
          <label class="mb-1 block text-xs font-medium text-text">Nom complet du joueur</label>
          <input v-model="newStat.player_name" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">PER</label>
          <input v-model="newStat.per" type="number" step="0.1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-text">MPG</label>
          <input v-model="newStat.mpg" type="number" step="0.1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
        </div>
      </div>
      <button
        type="button"
        class="min-h-11 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
        :disabled="isCreating"
        @click="createStat"
      >
        {{ isCreating ? 'Enregistrement…' : 'Ajouter' }}
      </button>
      <p v-if="createMessage" class="text-xs text-success">{{ createMessage }}</p>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <label class="text-sm font-medium text-text">Saison</label>
      <input
        v-model="filterSeason"
        type="text"
        placeholder="ex : 2024-2025"
        class="rounded-lg border border-border px-3 py-2 text-sm"
        @change="onFilterChange"
      />
      <label class="text-sm font-medium text-text">Joueur</label>
      <input
        v-model="filterPlayerName"
        type="text"
        placeholder="rechercher un nom"
        class="rounded-lg border border-border px-3 py-2 text-sm"
        @change="onFilterChange"
      />
    </div>

    <!-- Pager du HAUT : visible dès qu'il y a plus d'une page, y compris
         pendant isLoading (boutons alors désactivés, comme Réessayer) et
         donc AVANT la chaîne à cinq branches ci-dessous -- il ne se masque
         que via `showPager`, jamais via isLoading/loadFailed directement
         (voir le commentaire de `showPager`). -->
    <div v-if="showPager" class="flex items-center justify-between gap-2">
      <button
        type="button"
        class="min-h-11 rounded-lg border border-border px-3 py-2 text-sm font-medium disabled:opacity-50"
        :disabled="page <= 1 || isLoading"
        @click="goToPage(page - 1)"
      >
        Précédent
      </button>
      <p class="text-sm text-text-secondary">Page {{ page }} sur {{ totalPages }}</p>
      <button
        type="button"
        class="min-h-11 rounded-lg border border-border px-3 py-2 text-sm font-medium disabled:opacity-50"
        :disabled="page >= totalPages || isLoading"
        @click="goToPage(page + 1)"
      >
        Suivant
      </button>
    </div>

    <p v-if="isLoading" class="text-sm text-text-secondary">Chargement…</p>
    <!-- L'échec prend la PLACE des données, il ne se superpose pas à elles
         (§12) : ni liste, ni message de vide. Placé avant la branche du vide
         dans la chaîne, il l'exclut mécaniquement -- les deux s'affichaient
         ensemble jusqu'ici, et l'une des deux était fausse. -->
    <div v-else-if="loadFailed" role="alert" class="rounded-lg bg-danger/10 p-3">
      <p class="text-sm text-danger-text">{{ errorMessage }}</p>
      <!-- Relance le contexte COURANT (page incluse), sans rien changer à la
           sélection. -->
      <button
        type="button"
        class="mt-3 min-h-11 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
        :disabled="isLoading"
        @click="loadStats"
      >
        Réessayer
      </button>
    </div>

    <p v-else-if="total === 0" class="text-sm text-text-secondary">Aucune ligne pour ces filtres.</p>

    <!-- Page hors bornes : total > 0 mais cette page-ci n'a plus rien
         (ex : dernière ligne supprimée sans repli, cas transitoire couvert
         par deleteStat() -- ce bloc reste le filet si l'état s'affiche
         malgré tout). Distinct du vrai vide ci-dessus : affirmer "Aucune
         ligne pour ces filtres" ici serait faux, il EXISTE des lignes,
         seulement pas sur cette page (§12). -->
    <div v-else-if="stats.length === 0" class="rounded-lg bg-surface-sunken p-3">
      <p class="text-sm text-text-secondary">
        Cette page ne contient aucune ligne. {{ total }} ligne{{ total > 1 ? 's' : '' }} au total sous ces filtres.
      </p>
      <button
        type="button"
        class="mt-3 min-h-11 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
        :disabled="isLoading"
        @click="goToPage(1)"
      >
        Revenir à la première page
      </button>
    </div>

    <template v-else>
      <div v-for="stat in stats" :key="stat.id" class="space-y-3 rounded-xl border border-border bg-surface p-4">
        <div class="grid grid-cols-2 gap-3">
          <div class="col-span-2">
            <label class="mb-1 block text-xs font-medium text-text">Nom complet du joueur</label>
            <input v-model="forms[stat.id].player_name" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-text">Saison</label>
            <input v-model="forms[stat.id].season" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-text">Équipe (abréviation)</label>
            <input v-model="forms[stat.id].team_abbreviation" type="text" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-text">PER</label>
            <input v-model="forms[stat.id].per" type="number" step="0.1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-text">MPG</label>
            <input v-model="forms[stat.id].mpg" type="number" step="0.1" class="w-full rounded-lg border border-border px-3 py-2 text-sm" />
          </div>
        </div>

        <div class="flex gap-2">
          <button
            type="button"
            class="min-h-11 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-on disabled:opacity-50"
            :disabled="savingId === stat.id || deletingId === stat.id"
            @click="save(stat)"
          >
            {{ savingId === stat.id ? 'Enregistrement…' : 'Enregistrer' }}
          </button>
          <button
            type="button"
            class="min-h-11 rounded-lg border border-danger text-sm font-medium text-danger-text px-3 py-2 disabled:opacity-50"
            :disabled="savingId === stat.id || deletingId === stat.id"
            @click="deleteStat(stat)"
          >
            {{ deletingId === stat.id ? 'Suppression…' : 'Supprimer' }}
          </button>
        </div>
        <p v-if="savedId === stat.id" class="text-xs text-success">Enregistré.</p>
      </div>

      <!-- Pager du BAS : uniquement quand la liste est réellement affichée --
           une page fait ~10 écrans de téléphone, forcer un retour en haut
           pour avancer serait la même friction que ce chantier corrige. -->
      <div v-if="showPager" class="flex items-center justify-between gap-2">
        <button
          type="button"
          class="min-h-11 rounded-lg border border-border px-3 py-2 text-sm font-medium disabled:opacity-50"
          :disabled="page <= 1 || isLoading"
          @click="goToPage(page - 1)"
        >
          Précédent
        </button>
        <p class="text-sm text-text-secondary">Page {{ page }} sur {{ totalPages }}</p>
        <button
          type="button"
          class="min-h-11 rounded-lg border border-border px-3 py-2 text-sm font-medium disabled:opacity-50"
          :disabled="page >= totalPages || isLoading"
          @click="goToPage(page + 1)"
        >
          Suivant
        </button>
      </div>
    </template>
  </section>
</template>
