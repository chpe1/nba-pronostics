<script setup>
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import ThemeToggle from '@/components/ThemeToggle.vue'
import AdminNavMenu from '@/components/AdminNavMenu.vue'

const authStore = useAuthStore()
const router = useRouter()

function handleLogout() {
  authStore.logout()
  router.push({ name: 'dashboard' })
}
</script>

<template>
  <div class="flex min-h-screen flex-col bg-canvas text-text">
    <header class="border-b border-border bg-surface">
      <nav class="mx-auto flex max-w-2xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
        <RouterLink :to="{ name: 'dashboard' }" class="text-base font-semibold text-accent-text">
          Pronostics NBA
        </RouterLink>
        <div class="flex flex-wrap items-center gap-2 text-sm">
          <template v-if="authStore.isAuthenticated">
            <AdminNavMenu />
            <button
              type="button"
              class="flex h-11 items-center rounded-lg px-3 font-medium text-text-secondary hover:bg-surface-sunken"
              @click="handleLogout"
            >
              Déconnexion
            </button>
          </template>
          <RouterLink
            v-else
            :to="{ name: 'login' }"
            class="flex h-11 items-center rounded-lg px-3 font-medium text-text-secondary hover:bg-surface-sunken [&.router-link-exact-active]:text-accent-text"
          >
            Connexion admin
          </RouterLink>
          <ThemeToggle />
        </div>
      </nav>
    </header>

    <main class="flex-1">
      <RouterView />
    </main>
  </div>
</template>
