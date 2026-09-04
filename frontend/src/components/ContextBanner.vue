<script setup>
import { computed } from 'vue'
import DivergentGauge from './DivergentGauge.vue'
import { reliabilityTreatment } from '@/constants/reliability'

// Bandeau contextuel (docs/design-v1.md §9). Quatre états dans le document,
// deux implémentés ici (vitrine / non révélé) -- passé (§9.3) réutilise le
// bandeau vitrine tel quel (pas de bilan calculable), en cours (§9.4) n'a pas
// d'état correspondant dans le modèle Game. Rien à afficher si la journée est
// vide : DashboardView.vue porte déjà son propre message dédié pour ce cas.
const props = defineProps({
  games: { type: Array, required: true },
})

const revealedGames = computed(() => props.games.filter((g) => g.prediction && !g.prediction.is_upcoming))

// Vitrine (§9.2/§9.3) : le match au plus grand écart, calculé côté client sur
// la liste déjà reçue (voir plan-design-lot2.md, diagnostic Point 0.6) --
// aucun appel supplémentaire.
const showcaseGame = computed(() => {
  if (!revealedGames.value.length) return null
  return revealedGames.value.reduce((best, g) =>
    Math.abs(g.prediction.spread) > Math.abs(best.prediction.spread) ? g : best,
  )
})

// §9.2 : LE PRONOSTIC occupe la position dominante -- pas systématiquement l'équipe extérieure.
// Jusqu'ici le bandeau affichait toujours away puis home (comme GameCard.vue), une convention de
// lecture qui n'a de sens QUE parce que GameCard indique le favori par la couleur/le poids du
// texte, jamais par la position -- ici, la position EST le message ("mets en avant LE
// PRONOSTIC"), donc la reprendre telle quelle mettait en avant l'équipe battue à chaque fois que
// le favori était l'équipe extérieure (repéré en recette, 2026-08-31). Les deux notes portaient
// aussi la même couleur (text-accent-on hérité du fond, aucune distinction) -- contraire à §10.3
// ("celle du favori à l'accent, l'autre atténuée"), corrigé dans le même mouvement ci-dessous.
const winner = computed(() => {
  if (!showcaseGame.value) return null
  const g = showcaseGame.value
  const isHome = g.prediction.predicted_winner_team_id === g.home_team_id
  return {
    abbreviation: isHome ? g.home_team_abbreviation : g.away_team_abbreviation,
    note: isHome ? g.prediction.home_team_note : g.prediction.away_team_note,
  }
})
const loser = computed(() => {
  if (!showcaseGame.value) return null
  const g = showcaseGame.value
  const isHome = g.prediction.predicted_winner_team_id === g.home_team_id
  return {
    abbreviation: isHome ? g.away_team_abbreviation : g.home_team_abbreviation,
    note: isHome ? g.prediction.away_team_note : g.prediction.home_team_note,
  }
})

// Mention de confiance (§9.2) : même libellé/vocabulaire que la pastille des
// cartes (GameCard.vue) -- réutilise le même mapping (reliabilityTreatment),
// n'en crée pas un second. Ne change ni la sélection du match (toujours le
// plus grand écart) ni sa mise en avant : un match "Trop serré" reste
// affiché tel quel, juste étiqueté franchement -- comme une carte le fait
// déjà pour ce niveau (elle ne masque pas non plus le gagnant pronostiqué).
const mention = computed(() =>
  showcaseGame.value ? reliabilityTreatment(showcaseGame.value.prediction.reliability).mention : null,
)

// Non révélé (§9.1) : deux raisons distinctes, mais un même traitement visuel
// neutre -- priorité au message "aucun pronostic calculé" dès qu'au moins un
// match de la journée en relève (§9.1, décision consignée). Corrigé le
// 2026-08-30 : le message initial ("effectif en cours de chargement")
// évoquait à tort une attente passagère, alors que c'est un état stable de
// plusieurs semaines (§12) -- aligné sur le texte, déjà juste, de la carte.
const hasNeverCalculated = computed(() => props.games.some((g) => !g.prediction))
const upcomingCount = computed(() => props.games.filter((g) => g.prediction?.is_upcoming).length)
</script>

<template>
  <!-- Corps neutre coiffé d'une bande d'accent (§5.6/§9.2, 2026-09-04). L'aplat
       d'accent ne couvre plus tout le bandeau mais sa seule coiffe : la surface
       d'accent de l'écran passe de 16,0 % à 5,0 % (mesuré, deux modes, 1280 et
       390 px), sous la règle des 10 % du §5.6. `overflow-hidden` est structurel,
       pas cosmétique : sans lui, la coiffe déborde des coins arrondis. -->
  <div
    v-if="showcaseGame"
    class="mb-4 overflow-hidden rounded-xl border border-border bg-surface text-text"
  >
    <!-- La coiffe garde EXACTEMENT le couple accent-tint/accent-on d'avant :
         c'est ce qui préserve au centième les contrastes de la pastille déjà
         validés en recette (8,34:1 en sombre, 12,07:1 en clair) -- son fond ne
         change pas, donc ses valeurs non plus. -->
    <div class="flex items-center justify-between bg-accent-tint px-4 py-2 text-accent-on">
      <p class="text-xs font-medium">Pronostic du jour</p>
      <!-- Traitement uniforme (pas de couleur par niveau) : la coiffe est un aplat
           d'accent (§5.3, "l'orange est piégeux" en clair) -- y superposer les
           pastilles colorées des cartes (bg-warning/15, bg-neutral/15...) exposerait un rendu
           jamais mesuré sur ce fond précis. accent-on/accent-tint sont les deux seules valeurs
           mesurées et sûres dans les DEUX modes sur ce fond précis (voir docs/design-v1.md
           §9.2) : le même contraste sert donc aux trois niveaux, seul le libellé (mention)
           distingue "Confiance élevée"/"Confiance modérée"/"Trop serré" -- l'information ne
           repose jamais sur la seule couleur (§12), elle n'a ici tout simplement pas de couleur
           du tout à départager. -->
      <span class="rounded-full bg-accent-on/15 px-2 py-0.5 text-[11px] font-medium text-accent-on">
        {{ mention }}
      </span>
    </div>

    <div class="space-y-3 p-4">
      <div class="flex items-center justify-between font-title">
        <span>{{ winner.abbreviation }}</span>
        <span class="font-mono tabular-nums">{{ winner.note.toFixed(2) }}</span>
      </div>
      <DivergentGauge
        compact
        :home-note="showcaseGame.prediction.home_team_note"
        :away-note="showcaseGame.prediction.away_team_note"
        :home-team-abbreviation="showcaseGame.home_team_abbreviation"
        :away-team-abbreviation="showcaseGame.away_team_abbreviation"
        :threshold-high="showcaseGame.reliability_threshold_high"
      />
      <!-- Note atténuée : `text-text-secondary`, PAS l'ancien `text-accent-on/60`.
           Ce dernier valait #6E543B sur #FDBA74, soit 4,17:1 en sombre -- sous le
           seuil de 4,5:1, défaut jamais mesuré parce que validé à l'œil seul.
           Corrigé explicitement plutôt que laissé se résoudre par accident du
           changement de fond : 6,63:1 en sombre, 6,81:1 en clair. -->
      <div class="flex items-center justify-between font-title text-text-secondary">
        <span>{{ loser.abbreviation }}</span>
        <span class="font-mono tabular-nums">{{ loser.note.toFixed(2) }}</span>
      </div>
    </div>
  </div>

  <div v-else-if="games.length > 0" class="mb-4 rounded-xl bg-surface-sunken p-4 text-sm text-text-secondary">
    <template v-if="hasNeverCalculated">
      <p>Aucun pronostic calculé — l'effectif de la saison courante doit être importé, puis un
        recalcul lancé.</p>
      <!-- Secondaire, en retrait de la phrase ci-dessus : un complément
           d'information sur QUAND, pas une alerte. Distingue un état
           d'attente connue d'un état d'erreur, voir docs/design-v1.md §9.1. -->
      <p class="mt-1 text-xs text-text-disabled">
        Les rosters NBA ne se stabilisent qu'après les coupes d'effectif de présaison, mi-septembre
        — l'import ne sera possible qu'à partir de là.
      </p>
    </template>
    <p v-else>
      {{ upcomingCount }} match{{ upcomingCount > 1 ? 's' : '' }} programmé{{ upcomingCount > 1 ? 's' : '' }}
      — les pronostics seront révélés à l'approche de la date.
    </p>
  </div>
</template>
