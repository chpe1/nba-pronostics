import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { requiresAuthGuard } from './guard'
import DashboardView from '@/views/DashboardView.vue'
import LoginView from '@/views/LoginView.vue'
import AdminImportsView from '@/views/AdminImportsView.vue'
import AdminSettingsView from '@/views/AdminSettingsView.vue'
import AdminGamesView from '@/views/AdminGamesView.vue'
import AdminPlayersView from '@/views/AdminPlayersView.vue'
import AdminTeamDiagnosticView from '@/views/AdminTeamDiagnosticView.vue'
import AdminDatabaseView from '@/views/AdminDatabaseView.vue'
import AdminTeamsView from '@/views/AdminTeamsView.vue'
import AdminPreviousSeasonStatsView from '@/views/AdminPreviousSeasonStatsView.vue'

const routes = [
  { path: '/', name: 'dashboard', component: DashboardView },
  { path: '/login', name: 'login', component: LoginView },
  {
    path: '/admin/imports',
    name: 'admin-imports',
    component: AdminImportsView,
    meta: { requiresAuth: true },
  },
  {
    path: '/admin/settings',
    name: 'admin-settings',
    component: AdminSettingsView,
    meta: { requiresAuth: true },
  },
  {
    path: '/admin/games',
    name: 'admin-games',
    component: AdminGamesView,
    meta: { requiresAuth: true },
  },
  {
    path: '/admin/players',
    name: 'admin-players',
    component: AdminPlayersView,
    meta: { requiresAuth: true },
  },
  {
    path: '/admin/diagnostic',
    name: 'admin-team-diagnostic',
    component: AdminTeamDiagnosticView,
    meta: { requiresAuth: true },
  },
  {
    path: '/admin/database',
    name: 'admin-database',
    component: AdminDatabaseView,
    meta: { requiresAuth: true },
  },
  {
    path: '/admin/teams',
    name: 'admin-teams',
    component: AdminTeamsView,
    meta: { requiresAuth: true },
  },
  {
    path: '/admin/previous-season-stats',
    name: 'admin-previous-season-stats',
    component: AdminPreviousSeasonStatsView,
    meta: { requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const authStore = useAuthStore()
  return requiresAuthGuard(to, authStore.isAuthenticated)
})

export default router
