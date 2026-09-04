<script setup>
// Carte fantôme affichée pendant le chargement d'une journée (§13, ajoutée le
// 2026-09-04). Décalque la STRUCTURE de GameCard.vue -- même coquille, mêmes
// hauteurs de ligne, même emplacement de badge/note/jauge -- pour que la page
// garde sa forme au lieu de s'effondrer sur un écran noir le temps de la
// requête (mesuré : ~750px de vide sous la bande de dates, la grille ET le
// bandeau disparaissant ensemble).
//
// N'affirme RIEN sur le contenu : c'est la raison pour laquelle on affiche des
// blocs vides plutôt que de conserver la liste précédente. Garder les matchs de
// la veille sous une date déjà changée dans la bande afficherait une
// information fausse -- ce que ce produit refuse partout ailleurs (masquage
// `is_upcoming` §10.3, mention "Trop serré" assumée §10.2, glyphe aligné sur
// son libellé §12).
//
// `aria-hidden` : la zone parente porte déjà l'annonce accessible
// ("Chargement des matchs…", DashboardView.vue) -- ces blocs décoratifs
// n'ont rien à dire de plus à un lecteur d'écran.
</script>

<template>
  <article
    class="skeleton-pulse rounded-xl border border-border bg-surface p-4 shadow-sm"
    aria-hidden="true"
  >
    <!-- Ligne 1 : heure à gauche, pastille de confiance à droite -->
    <div class="mb-3 flex items-center justify-between">
      <div class="h-4 w-12 rounded bg-surface-sunken" />
      <div class="h-6 w-28 rounded-full bg-surface-sunken" />
    </div>

    <!-- Deux lignes d'équipe : badge 40px + tricode, note à droite -->
    <div class="space-y-2">
      <div v-for="row in 2" :key="row" class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <div class="h-10 w-10 shrink-0 rounded-lg bg-surface-sunken" />
          <div class="h-5 w-16 rounded bg-surface-sunken" />
        </div>
        <div class="h-5 w-14 rounded bg-surface-sunken" />
      </div>
    </div>

    <!-- Jauge divergente -->
    <div class="my-3 h-2 w-full rounded-full bg-surface-sunken" />

    <!-- Écart projeté -->
    <div class="mt-3 border-t border-border pt-2">
      <div class="h-4 w-36 rounded bg-surface-sunken" />
    </div>
  </article>
</template>
