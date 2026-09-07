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
      <nav class="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
        <RouterLink
          :to="{ name: 'dashboard' }"
          class="press-feedback inline-flex h-11 items-center gap-2 text-base font-semibold text-accent-text"
        >
          <svg
            class="h-7 w-7 shrink-0"
            aria-hidden="true"
            viewBox="0 0 64 64"
            width="28"
            height="28"
          >
            <defs>
              <clipPath id="header-brand-ball">
                <circle cx="45.01" cy="18.15" r="7" />
              </clipPath>
            </defs>
            <!-- part adverse : texte atténué, délibérément sourd -- subordonné au favori -->
            <path
              d="M48.32 22.27 A19 19 0 0 1 45.44 45.44"
              fill="none"
              stroke="var(--text-disabled)"
              stroke-width="7.5"
              stroke-linecap="round"
            />
            <path
              d="M18.57 45.44 A19 19 0 0 1 45.01 18.15"
              fill="none"
              stroke="var(--accent-fill, #F97316)"
              stroke-width="7.5"
              stroke-linecap="round"
            />
            <circle cx="45.01" cy="18.15" r="7" fill="var(--accent-fill, #F97316)" />
            <!-- coutures : couleur de surface, pas currentColor -- creusent le ballon
                 comme des entailles, suivent le thème, indépendantes de l'axe d'accent -->
            <g
              clip-path="url(#header-brand-ball)"
              fill="none"
              stroke="var(--surface)"
              stroke-width="1.5"
              stroke-linecap="round"
            >
              <path d="M45.01 10.9 C41.3 14.3 41.3 22 45.01 25.4" />
              <path d="M38 18.15 C41.4 15.7 48.6 15.7 52.02 18.15" />
            </g>
          </svg>
          Pronostics NBA
        </RouterLink>
        <div class="flex flex-wrap items-center gap-2 text-sm">
          <template v-if="authStore.isAuthenticated">
            <AdminNavMenu />
            <button
              type="button"
              class="press-feedback flex h-11 items-center rounded-lg px-3 font-medium text-text-secondary hover:bg-surface-sunken"
              @click="handleLogout"
            >
              Déconnexion
            </button>
          </template>
          <RouterLink
            v-else
            :to="{ name: 'login' }"
            class="press-feedback flex h-11 items-center rounded-lg px-3 font-medium text-text-secondary hover:bg-surface-sunken [&.router-link-exact-active]:text-accent-text"
          >
            Connexion admin
          </RouterLink>
          <ThemeToggle />
        </div>
      </nav>
    </header>

    <main class="mx-auto w-full max-w-7xl flex-1">
      <RouterView />
    </main>
  </div>
</template>
