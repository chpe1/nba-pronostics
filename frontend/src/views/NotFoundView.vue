<script setup>
import { RouterLink } from 'vue-router'
</script>

<template>
  <section class="mx-auto max-w-2xl space-y-4 px-4 py-12 text-center">
    <p class="text-sm font-medium text-accent-text">404</p>
    <h1 class="text-xl font-semibold text-text">Page introuvable</h1>
    <p class="text-sm text-text-secondary">
      L'adresse demandée ne correspond à aucun écran de l'application.
    </p>
    <RouterLink
      :to="{ name: 'dashboard' }"
      class="inline-flex h-11 items-center rounded-lg bg-accent px-4 text-sm font-medium text-accent-on hover:opacity-90"
    >
      Retour au tableau de bord
    </RouterLink>
  </section>
</template>
