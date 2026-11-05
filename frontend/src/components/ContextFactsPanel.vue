<script setup>
// Liste COMPLÈTE des faits de contexte d'une équipe (absents, calendrier, incertains), ouverte par le bouton « +N » de
// GameCard.vue. Une ligne en tête nomme l'équipe (sans elle, le panneau pleine largeur peut se lire comme un résumé du
// match) et sert de nom à la région (aria-labelledby) : un lecteur d'écran l'annonce à l'entrée. Un titre en toutes
// lettres par groupe dit s'il pèse sur la note : la nature d'un fait est portée par sa teinte, le fait qu'il compte par
// son remplissage (pleine = pèse, contour pointillé = sans effet), et les deux par le texte du titre, jamais par la
// couleur seule. Les classes des pastilles sont reçues toutes faites de la carte.
defineProps({
  id: { type: String, required: true },
  team: { type: String, required: true },
  groups: { type: Array, required: true },
})
</script>

<template>
  <div :id="id" role="region" :aria-labelledby="`${id}-team`" class="space-y-2" data-testid="facts-panel">
    <p :id="`${id}-team`" class="font-title text-sm text-text" data-testid="facts-team">{{ team }}</p>
    <section v-for="g in groups" :key="g.kind" :data-testid="`facts-group-${g.kind}`">
      <p class="text-xs font-medium text-text-secondary">{{ g.title }}</p>
      <div class="mt-1 flex flex-wrap gap-1">
        <span v-for="f in g.items" :key="f.key" :class="f.cls" data-testid="fact-pill" :data-kind="f.kind">
          {{ f.text }}
        </span>
      </div>
    </section>
  </div>
</template>
