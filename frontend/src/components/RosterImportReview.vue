<script setup>
import { computed, watch } from 'vue'
import {
  associatedPlayerIds,
  detachmentBlockReasons,
  groupByTeam,
  hasVerdict,
  unresolvedRows,
} from '@/utils/rosterVerdicts'

// Aperçu d'un import d'EFFECTIF (type ROSTER) lu dans l'ordre des DÉCISIONS, pas dans l'ordre des
// données (Décision d'architecture n°39) : d'abord les lignes à trancher (elles bloquent tout le reste),
// puis les lignes en erreur (elles aussi), puis les joueurs à détacher. Le reste du récapitulatif est
// rendu par CsvUploadForm.vue, en dessous.
//
// Aucun choix n'est jamais pris par défaut : ni verdict, ni case cochée.
//
// ORDRE : les lignes en erreur passent AVANT les lignes à trancher. Une erreur se répare dans le
// fichier et impose de le réimporter (donc de refaire l'aperçu, qui remet tous les verdicts à zéro) :
// trancher des verdicts avant de l'avoir corrigée est du travail perdu.

const props = defineProps({
  preview: { type: Object, required: true },
})

// État propriétaire : CsvUploadForm.vue (il en a besoin pour le libellé du bouton et l'envoi).
const verdicts = defineModel('verdicts', { type: Object, required: true })
const selectedIds = defineModel('selectedIds', { type: Array, required: true })

const rows = computed(() => props.preview.file_rows_without_match ?? [])
// Règle du serveur (une seule source de vérité) : verdicts obligatoires quand il existe à la fois une
// ligne sans correspondance ET un joueur de la base absent du fichier.
const verdictsRequired = computed(() => props.preview.verdicts_required === true)
const candidates = computed(() => props.preview.association_candidates ?? [])
const rowErrors = computed(() => props.preview.row_errors ?? [])

const unresolved = computed(() => unresolvedRows(rows.value, verdicts.value))

// Verdicts obligatoires : on annonce ce qui MANQUE (c'est ce qui bloque). Verdicts facultatifs : rien ne
// bloque, on annonce la CONSÉQUENCE plutôt qu'un manque alarmiste.
const counterText = computed(() => {
  if (!unresolved.value.length) return `Les ${rows.value.length} ligne(s) ont un verdict.`
  if (verdictsRequired.value) return `${unresolved.value.length} ligne(s) sur ${rows.value.length} restent sans verdict.`
  return `${unresolved.value.length} ligne(s) sans verdict — elles seront importées comme recrues.`
})
const associatedIds = computed(() => associatedPlayerIds(verdicts.value))

// Un joueur associé à une ligne du fichier EST dans le fichier : il n'est plus détachable.
const detachable = computed(() => (props.preview.detachable ?? []).filter((p) => !associatedIds.value.has(p.id)))
const groups = computed(() => groupByTeam(detachable.value))

const blockReasons = computed(() =>
  detachmentBlockReasons({ unresolvedCount: unresolved.value.length, errorCount: rowErrors.value.length }),
)
const blocked = computed(() => blockReasons.value.length > 0)

// Dès que le détachement devient impossible, ou qu'un joueur coché devient associé, on retire les cases
// concernées : l'écran n'envoie jamais un identifiant que le serveur refuserait.
watch([blocked, associatedIds], () => {
  const valid = new Set(detachable.value.map((p) => p.id))
  const kept = blocked.value ? [] : selectedIds.value.filter((id) => valid.has(id))
  if (kept.length !== selectedIds.value.length) selectedIds.value = kept
})

function setKind(row, kind) {
  const current = verdicts.value[row.name] ?? { kind: null, playerId: null }
  verdicts.value = {
    ...verdicts.value,
    [row.name]: { kind, playerId: kind === 'recruit' ? null : current.playerId },
  }
}

// Sélecteur : `:value` + gestionnaire dédié, JAMAIS v-model (Décision d'architecture n°31 : sur un
// <select>, v-model et @change se disputent le même événement `change`).
function onSelectPlayer(row, event) {
  const raw = event.target.value
  verdicts.value = {
    ...verdicts.value,
    [row.name]: { kind: 'same_player', playerId: raw === '' ? null : Number(raw) },
  }
}

function suggestedCandidate(row) {
  return candidates.value.find((c) => c.name === row.closest_absent_player) ?? null
}
function otherCandidates(row) {
  const suggestion = suggestedCandidate(row)
  return candidates.value.filter((c) => !suggestion || c.id !== suggestion.id)
}
// Un joueur déjà choisi pour une AUTRE ligne n'est plus proposé (le serveur refuse deux lignes vers le même joueur).
function takenByAnotherRow(row, candidate) {
  return Object.entries(verdicts.value).some(
    ([name, verdict]) => name !== row.name && verdict.kind === 'same_player' && verdict.playerId === candidate.id,
  )
}
function candidateLabel(candidate) {
  return `${candidate.name} (${candidate.team_abbreviation ?? 'agent libre'})`
}

function isChecked(player) {
  return selectedIds.value.includes(player.id)
}
function toggle(player, event) {
  const checked = event.target.checked
  const others = selectedIds.value.filter((id) => id !== player.id)
  selectedIds.value = checked ? [...others, player.id] : others
}
function checkAll() {
  if (blocked.value) return
  selectedIds.value = detachable.value.map((p) => p.id)
}
function uncheckAll() {
  selectedIds.value = []
}

function formatN1(player) {
  if (player.per_n1 === null || player.per_n1 === undefined) return 'pas de ligne N-1'
  return `PER N-1 ${player.per_n1.toFixed(1)} · MPG N-1 ${player.mpg_n1.toFixed(1)}`
}
</script>

<template>
  <div class="space-y-4">
    <!-- 1. LIGNES EN ERREUR : en premier -- elles se réparent dans le fichier et obligent à refaire l'aperçu -->
    <section
      v-if="rowErrors.length"
      data-testid="section-errors"
      class="rounded-lg border border-warning bg-warning/10 p-3 text-text"
    >
      <h3 class="font-semibold">Lignes en erreur ({{ rowErrors.length }})</h3>
      <p class="mt-1">
        <strong>Tout détachement est bloqué</strong> tant que ces lignes sont dans le fichier : un nom illisible
        pourrait être un joueur « absent » à tort. Corrigez le fichier, puis refaites l'aperçu.
      </p>
      <ul class="mt-2 space-y-1">
        <li v-for="error in rowErrors" :key="error.row" data-testid="row-error">
          <strong>Ligne {{ error.row }}</strong> du fichier — nom : « {{ error.player_name ?? '(vide)' }} », équipe :
          « {{ error.team ?? '(vide)' }} » — {{ error.message }}
        </li>
      </ul>
    </section>

    <!-- 2. LIGNES À TRANCHER : visibles sans dépliage -->
    <section data-testid="section-rows" class="rounded-lg border border-border p-3">
      <h3 class="font-semibold text-text">Lignes à trancher ({{ rows.length }})</h3>
      <template v-if="rows.length">
        <p v-if="verdictsRequired" class="mt-1 text-text-secondary">
          Ces lignes du fichier ne correspondent à aucun joueur actif de la base : c'est soit une recrue, soit un
          joueur déjà en base sous un autre nom. Chaque ligne demande un verdict, un par un — aucun geste global — et
          l'import ne peut pas être confirmé tant qu'il en reste une sans verdict.
        </p>
        <p v-else class="mt-1 text-text-secondary" data-testid="rows-optional-note">
          Ces lignes du fichier ne correspondent à aucun joueur actif de la base, et aucun joueur de la base n'est absent
          du fichier : ce ne peuvent être que des recrues. Le verdict est facultatif ; sans verdict, la ligne est importée
          comme une recrue.
        </p>
        <p
          data-testid="rows-counter"
          class="mt-2 font-medium"
          :class="unresolved.length ? 'text-text' : 'text-text-secondary'"
        >
          {{ counterText }}
        </p>
        <p
          v-if="unresolved.length && verdictsRequired"
          data-testid="rows-block-notice"
          role="status"
          class="mt-2 rounded-lg border border-warning bg-warning/10 px-3 py-2 text-text"
        >
          <strong>La confirmation et le détachement sont impossibles</strong> tant qu'il reste une ligne sans verdict :
          un joueur absent du fichier pourrait être l'une de ces lignes, écrite autrement (ex. « Ronald Holland II »
          pour « Ron Holland »), et serait alors dupliqué.
        </p>

        <ul class="mt-3 space-y-3">
          <li
            v-for="(row, index) in rows"
            :key="row.name"
            data-testid="row-to-decide"
            class="rounded-lg border border-border bg-surface-sunken p-3"
          >
            <fieldset>
              <legend class="mb-1 font-medium text-text">
                {{ row.name }} <span class="text-text-secondary">— {{ row.team_abbreviation }}</span>
                <span v-if="hasVerdict(verdicts[row.name])" class="ml-1 text-text-secondary">· tranchée</span>
              </legend>

              <label class="flex min-h-11 items-center gap-2">
                <input
                  type="radio"
                  :name="`verdict-${index}`"
                  value="recruit"
                  :checked="verdicts[row.name]?.kind === 'recruit'"
                  @change="setKind(row, 'recruit')"
                />
                C'est une recrue
              </label>

              <label class="flex min-h-11 items-center gap-2">
                <input
                  type="radio"
                  :name="`verdict-${index}`"
                  value="same_player"
                  :checked="verdicts[row.name]?.kind === 'same_player'"
                  @change="setKind(row, 'same_player')"
                />
                C'est le même joueur que…
              </label>

              <select
                :aria-label="`Joueur de la base correspondant à ${row.name}`"
                :value="verdicts[row.name]?.playerId ?? ''"
                :disabled="verdicts[row.name]?.kind !== 'same_player'"
                class="mt-1 min-h-11 w-full rounded-lg border border-border px-2 py-1 text-sm disabled:opacity-50"
                @change="onSelectPlayer(row, $event)"
              >
                <option value="">— choisir un joueur de la base —</option>
                <optgroup v-if="suggestedCandidate(row)" label="Suggestion (ressemblance de noms — à vérifier)">
                  <option
                    :value="suggestedCandidate(row).id"
                    :disabled="takenByAnotherRow(row, suggestedCandidate(row))"
                  >
                    ★ {{ candidateLabel(suggestedCandidate(row)) }}
                  </option>
                </optgroup>
                <optgroup label="Joueurs de la base absents du fichier">
                  <option
                    v-for="candidate in otherCandidates(row)"
                    :key="candidate.id"
                    :value="candidate.id"
                    :disabled="takenByAnotherRow(row, candidate)"
                  >
                    {{ candidateLabel(candidate) }}
                  </option>
                </optgroup>
              </select>
              <p v-if="suggestedCandidate(row)" class="mt-1 text-xs text-text-secondary">
                ★ Suggestion : {{ suggestedCandidate(row).name }} — jamais présélectionnée.
              </p>
            </fieldset>
          </li>
        </ul>
      </template>
      <p v-else class="mt-1 text-text-secondary" data-testid="rows-none">
        Aucune ligne sans correspondance : tout joueur absent du fichier est réellement parti.
      </p>
    </section>

    <!-- 3. JOUEURS À DÉTACHER : nominatif, groupé par équipe, aucune case cochée par défaut -->
    <section data-testid="section-detach" class="rounded-lg border border-border p-3">
      <h3 class="font-semibold text-text">Joueurs à détacher ({{ detachable.length }})</h3>
      <template v-if="detachable.length">
        <p class="mt-1 text-text-secondary">
          Joueurs de la base absents du fichier : ils deviendraient agents libres (ils restent en base, détachés de
          leur équipe, et ne pèsent plus sur elle). Aucune case n'est cochée par défaut.
        </p>

        <div class="mt-2 flex flex-wrap items-center gap-2">
          <button
            type="button"
            data-testid="check-all"
            class="min-h-11 rounded-lg border border-border px-3 py-2 text-sm font-medium disabled:opacity-50"
            :disabled="blocked"
            @click="checkAll"
          >
            Tout cocher
          </button>
          <button
            type="button"
            data-testid="uncheck-all"
            class="min-h-11 rounded-lg border border-border px-3 py-2 text-sm font-medium disabled:opacity-50"
            :disabled="blocked"
            @click="uncheckAll"
          >
            Tout décocher
          </button>
          <span class="text-text-secondary" data-testid="checked-counter">
            {{ selectedIds.length }} coché(s) sur {{ detachable.length }}
          </span>
        </div>

        <div v-if="blocked" data-testid="detach-block-notice" role="status" class="mt-2 text-text">
          <p class="font-medium">
            « Tout cocher », « Tout décocher » et les cases sont désactivés : le détachement est impossible.
          </p>
          <ul class="ml-4 list-disc">
            <li v-for="reason in blockReasons" :key="reason">{{ reason }}</li>
          </ul>
        </div>

        <div v-for="group in groups" :key="group.team" class="mt-3" data-testid="detach-group">
          <h4 class="font-medium text-text">{{ group.team }} — {{ group.players.length }} joueur(s)</h4>
          <ul class="divide-y divide-border">
            <li v-for="player in group.players" :key="player.id">
              <label class="flex min-h-11 items-start gap-2 py-2">
                <input
                  type="checkbox"
                  class="mt-0.5"
                  :checked="isChecked(player)"
                  :disabled="blocked"
                  @change="toggle(player, $event)"
                />
                <span class="text-text">
                  {{ player.name }}
                  <span class="text-text-secondary">
                    — {{ player.team_abbreviation }} · {{ formatN1(player)
                    }}<template v-if="player.draft_pick !== null"> · pick {{ player.draft_pick }}</template>
                  </span>
                </span>
              </label>
            </li>
          </ul>
        </div>
      </template>
      <p v-else class="mt-1 text-text-secondary" data-testid="detach-none">Aucun joueur à détacher.</p>
    </section>
  </div>
</template>
