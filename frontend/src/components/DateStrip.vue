<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

// Habillage du sélecteur de date existant (docs/design-v1.md §8.4) : envoie
// exactement la même valeur `YYYY-MM-DD` que l'ancien <input type="date">,
// jamais un paramètre différent -- v-model porte la même chaîne ISO.
//
// Deux métiers, deux widgets (§8.4, décision du 2026-08-30) : la bande sert à
// PARCOURIR les jours proches, le champ de date natif sert à SAUTER à une date
// quelconque -- capacité perdue en remplaçant l'ancien <input type="date">
// (deux clics pour n'importe quelle date) par la seule bande (une dizaine de
// balayages pour atteindre J+14), alors que le calendrier complet 2026-2027
// est déjà en base.
const props = defineProps({
  modelValue: { type: String, required: true },
})
const emit = defineEmits(['update:modelValue'])

// Fenêtre resserrée sur le seuil de révélation, pas une valeur ronde : miroir
// de PREDICTION_REVEAL_THRESHOLD_DAYS (app/api/predictions.py) -- à
// resynchroniser manuellement si cette constante backend change, comme pour
// toute autre valeur dupliquée entre les deux côtés de ce projet.
const REVEAL_THRESHOLD_DAYS = 2
const WINDOW_BEFORE = 7
const WINDOW_AFTER = REVEAL_THRESHOLD_DAYS + 1 // premier jour masqué inclus, pour que la frontière se voie

function toIsoDate(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function parseIsoDate(iso) {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day)
}

const todayIso = toIsoDate(new Date())
const todayYear = new Date().getFullYear()

function daysAhead(iso) {
  return Math.round((parseIsoDate(iso) - parseIsoDate(todayIso)) / 86400000)
}

const dates = computed(() => {
  const center = parseIsoDate(props.modelValue)
  const list = []
  for (let offset = -WINDOW_BEFORE; offset <= WINDOW_AFTER; offset += 1) {
    const d = new Date(center)
    d.setDate(d.getDate() + offset)
    list.push(toIsoDate(d))
  }
  return list
})

// Séparation visible au changement de mois + marquage des jours au-delà du
// seuil de révélation (§8.4, §9.1) -- ni l'un ni l'autre ne doivent reposer
// sur la seule couleur (§12), voir accessibleLabel() et le contour en
// pointillés (jamais un simple assombrissement, qui les ferait passer pour
// désactivés alors qu'ils restent cliquables et mènent à un état légitime).
//
// Le marquage ne s'affiche QUE si la fenêtre contient à la fois des jours
// révélés/passés et des jours masqués -- corrigé le 2026-08-30 : avant
// l'ouverture de la saison, tous les jours de la fenêtre sont masqués (aucune
// frontière n'est réellement visible dans la bande), le marquage uniforme sur
// les 11 jours n'apportait alors aucune information -- c'est le bandeau
// contextuel qui porte déjà ce cas (§9.1).
const hasMixedThreshold = computed(() => {
  const flags = dates.value.map((iso) => daysAhead(iso) > REVEAL_THRESHOLD_DAYS)
  return flags.some(Boolean) && flags.some((flag) => !flag)
})

const dateItems = computed(() =>
  dates.value.map((iso, index) => {
    const startsNewMonth = index > 0 && parseIsoDate(iso).getMonth() !== parseIsoDate(dates.value[index - 1]).getMonth()
    const isBeyondThreshold = hasMixedThreshold.value && daysAhead(iso) > REVEAL_THRESHOLD_DAYS
    return { iso, startsNewMonth, isBeyondThreshold }
  }),
)

function dayLabel(iso) {
  const d = parseIsoDate(iso)
  return {
    weekday: d.toLocaleDateString('fr-FR', { weekday: 'short' }),
    day: d.getDate(),
  }
}

function accessibleLabel(item) {
  if (!item.isBeyondThreshold) return null
  const formatted = parseIsoDate(item.iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long' })
  return `${formatted} — pronostic pas encore révélé à cette date (au-delà du seuil de révélation)`
}

const itemRefs = ref({})
function setItemRef(iso, el) {
  if (el) itemRefs.value[iso] = el
}

function scrollToSelected(behavior = 'smooth') {
  itemRefs.value[props.modelValue]?.scrollIntoView({ inline: 'center', block: 'nearest', behavior })
  // Resynchronisation explicite, pas seulement l'évènement 'scroll' passif ci-dessous : vérifié en
  // navigateur (2026-08-31, ≥1280px) que quand les 11 jours tiennent déjà entièrement dans le
  // conteneur, scrollIntoView() ne bouge rien et ne déclenche donc AUCUN évènement 'scroll' --
  // visibleIso restait alors bloqué indéfiniment sur son ancienne valeur, désynchronisé du jour
  // réellement au centre visuel (cause du libellé de mois faux, repéré en recette). Pour le cas
  // 'smooth' où un vrai défilement a lieu, cet appel immédiat donne une valeur provisoire qui sera
  // affinée par les évènements 'scroll' réels de l'animation, sans régression.
  updateVisibleFromScroll()
}

watch(() => props.modelValue, () => nextTick(() => scrollToSelected()))
onMounted(() => nextTick(() => scrollToSelected('instant')))

function onJumpToDate(event) {
  emit('update:modelValue', event.target.value)
}

// Libellé de mois : reflète la date actuellement VISIBLE au centre de la
// bande pendant le défilement, pas seulement la date sélectionnée -- sinon le
// libellé reste faux tant qu'on n'a pas cliqué après avoir fait défiler.
const stripRef = ref(null)
const visibleIso = ref(props.modelValue)
watch(() => props.modelValue, (value) => {
  visibleIso.value = value
})

function updateVisibleFromScroll() {
  const container = stripRef.value
  if (!container) return
  const containerRect = container.getBoundingClientRect()
  // Le conteneur (flex, display de bloc) s'étire à la largeur de SON PARENT même quand les 11
  // jours ne la remplissent pas (constaté en navigateur, >=1280px : la carte est bien plus large
  // que les 11 boutons, empaquetés à gauche par le flex par défaut) -- centrer sur la largeur du
  // conteneur placerait alors le "centre" loin à droite des boutons, et la recherche du plus
  // proche retombait toujours sur le DERNIER jour affiché, jamais le jour réellement au centre
  // visuel (cause du libellé de mois faux/incohérent constaté en recette). `scrollWidth` ne sert
  // pas à distinguer les deux cas : pour un conteneur dont le contenu ne déborde pas, il vaut la
  // largeur du conteneur lui-même (vérifié en navigateur), pas celle du contenu réel -- mesuré ici
  // directement sur les boutons rendus (premier/dernier jour de la fenêtre courante).
  const isos = dates.value
  const firstEl = itemRefs.value[isos[0]]
  const lastEl = itemRefs.value[isos[isos.length - 1]]
  let centerX = containerRect.left + containerRect.width / 2
  if (firstEl && lastEl) {
    const contentLeft = firstEl.getBoundingClientRect().left
    const contentRight = lastEl.getBoundingClientRect().right
    if (contentRight - contentLeft <= containerRect.width) {
      centerX = contentLeft + (contentRight - contentLeft) / 2
    }
  }
  let closestIso = null
  let closestDistance = Infinity
  for (const iso of dates.value) {
    const el = itemRefs.value[iso]
    if (!el) continue
    const rect = el.getBoundingClientRect()
    const distance = Math.abs(rect.left + rect.width / 2 - centerX)
    if (distance < closestDistance) {
      closestDistance = distance
      closestIso = iso
    }
  }
  if (closestIso) visibleIso.value = closestIso
}

const monthLabel = computed(() => {
  const d = parseIsoDate(visibleIso.value)
  const label = d.toLocaleDateString('fr-FR', {
    month: 'long',
    year: d.getFullYear() !== todayYear ? 'numeric' : undefined,
  })
  return label.charAt(0).toUpperCase() + label.slice(1)
})
</script>

<template>
  <div>
    <div class="mb-1 flex items-center justify-between gap-2">
      <p class="text-xs font-medium text-text-secondary" aria-live="polite">{{ monthLabel }}</p>
      <input
        type="date"
        :value="modelValue"
        class="rounded border border-border bg-transparent px-1 py-0.5 text-xs text-text-secondary"
        aria-label="Aller à une date précise"
        @change="onJumpToDate"
      />
    </div>
    <div
      ref="stripRef"
      class="scrollbar-none flex snap-x snap-mandatory gap-2 overflow-x-auto pb-1"
      role="listbox"
      aria-label="Sélection de la date consultée"
      @scroll="updateVisibleFromScroll"
    >
      <button
        v-for="item in dateItems"
        :key="item.iso"
        :ref="(el) => setItemRef(item.iso, el)"
        type="button"
        role="option"
        :aria-selected="item.iso === modelValue"
        :aria-label="accessibleLabel(item)"
        class="flex h-14 w-12 shrink-0 snap-center flex-col items-center justify-center rounded-lg text-xs"
        :class="[
          item.iso === modelValue ? 'bg-accent font-medium text-accent-on' : 'bg-surface-sunken text-text-secondary',
          item.startsNewMonth ? 'ml-2 border-l border-border pl-1' : '',
          item.isBeyondThreshold ? 'outline outline-1 outline-dashed outline-offset-1 outline-border' : '',
        ]"
        @click="emit('update:modelValue', item.iso)"
      >
        <span class="capitalize">{{ dayLabel(item.iso).weekday }}</span>
        <span
          class="font-mono text-sm tabular-nums"
          :class="item.iso === todayIso && item.iso !== modelValue ? 'text-accent-text' : ''"
        >
          {{ dayLabel(item.iso).day }}
        </span>
      </button>
    </div>
  </div>
</template>
