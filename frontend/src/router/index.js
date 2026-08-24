import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { requiresAuthGuard } from './guard'
import DashboardView from '@/views/DashboardView.vue'
import LoginView from '@/views/LoginView.vue'
import AdminImportsView from '@/views/AdminImportsView.vue'
import AdminSettingsView from '@/views/AdminSettingsView.vue'
import AdminGamesView from '@/views/AdminGamesView.vue'

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
