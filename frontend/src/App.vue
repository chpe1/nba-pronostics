<script setup>
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const router = useRouter()

function handleLogout() {
  authStore.logout()
  router.push({ name: 'dashboard' })
}
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <nav class="border-b border-gray-200 bg-white px-4 py-3">
      <div class="mx-auto flex max-w-2xl items-center justify-between text-sm">
        <RouterLink to="/" class="font-semibold text-gray-900">Pronostics NBA</RouterLink>
        <div class="flex items-center gap-4">
          <template v-if="authStore.isAuthenticated">
            <RouterLink to="/admin/imports" class="text-gray-600">Imports</RouterLink>
            <RouterLink to="/admin/games" class="text-gray-600">Matchs</RouterLink>
            <RouterLink to="/admin/players" class="text-gray-600">Joueurs</RouterLink>
            <RouterLink to="/admin/teams" class="text-gray-600">Équipes</RouterLink>
            <RouterLink to="/admin/previous-season-stats" class="text-gray-600">Stats N-1</RouterLink>
            <RouterLink to="/admin/diagnostic" class="text-gray-600">Diagnostic équipes</RouterLink>
            <RouterLink to="/admin/database" class="text-gray-600">Base de données</RouterLink>
            <RouterLink to="/admin/settings" class="text-gray-600">Réglages généraux de l'algorithme</RouterLink>
            <button type="button" class="text-gray-600" @click="handleLogout">Déconnexion</button>
          </template>
          <RouterLink v-else to="/login" class="text-gray-600">Connexion admin</RouterLink>
        </div>
      </div>
    </nav>

    <RouterView />
  </div>
</template>
