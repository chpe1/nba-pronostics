<script setup>
defineProps({
  history: {
    type: Array,
    required: true,
  },
})

// Statut : jamais porté par la seule couleur (§12) -- un libellé français
// explicite accompagne toujours la pastille colorée.
const STATUS_STYLES = {
  success: 'bg-success/15 text-success',
  partial: 'bg-warning/15 text-warning',
  error: 'bg-danger/15 text-danger-text',
}
const STATUS_LABELS = {
  success: 'Réussi',
  partial: 'Partiel',
  error: 'Échec',
}

function formatDate(value) {
  return new Date(value).toLocaleString('fr-FR')
}
</script>

<template>
  <div class="rounded-xl border border-border bg-surface p-4">
    <h2 class="mb-3 text-sm font-semibold text-text">Historique des imports</h2>

    <p v-if="history.length === 0" class="text-sm text-text-secondary">Aucun import pour l'instant.</p>

    <!-- Liste de cartes, pas un <table> (§15) : à 653px de contenu minimum mesuré
         (§15a), ce tableau à 6 colonnes dépasse déjà la largeur maximale que cet
         écran peut jamais offrir (max-w-2xl, 608px de contenu au mieux) -- aucun
         seuil de viewport ne le ferait un jour tenir en table, la bascule n'est
         donc pas responsive, c'est un remplacement pur. Hiérarchie : statut
         d'abord (dominant), date+type juste en dessous, lignes ensuite,
         fichier+saison en texte secondaire -- rien n'est supprimé. -->
    <!-- Pas de bg-surface ici : ce conteneur est déjà posé sur une carte
         (bg-surface du conteneur parent) -- lui redonner la même couleur de fond
         le rendrait indiscernable de son propre parent (voir la note sur
         --surface-sunken en style.css, même famille de piège). La bordure seule
         suffit à délimiter chaque entrée, comme sur n'importe quel élément posé
         directement sur la page ailleurs dans l'appli. -->
    <div v-else class="space-y-2">
      <div v-for="entry in history" :key="entry.id" class="space-y-1 rounded-xl border border-border p-3">
        <span
          class="inline-flex rounded-full px-2 py-0.5 text-sm font-semibold"
          :class="STATUS_STYLES[entry.status]"
        >
          {{ STATUS_LABELS[entry.status] }}
        </span>
        <div class="flex items-center justify-between gap-2 text-sm text-text">
          <span class="tabular-nums">{{ formatDate(entry.created_at) }}</span>
          <span>{{ entry.import_type }}</span>
        </div>
        <p class="text-sm text-text-secondary tabular-nums">
          {{ entry.row_count }} ligne(s)<span v-if="entry.error_count">, {{ entry.error_count }} erreur(s)</span>
        </p>
        <p class="truncate text-xs text-text-disabled">
          {{ entry.filename }} — saison {{ entry.season ?? 'courante' }}
        </p>
      </div>
    </div>
  </div>
</template>
