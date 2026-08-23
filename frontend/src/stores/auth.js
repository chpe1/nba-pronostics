import { defineStore } from 'pinia'
import { apiFetch } from '@/services/apiClient'

// Token en mémoire uniquement (pas de persistance localStorage) : perdu au
// rechargement de page, ce qui est le comportement voulu pour ce MVP.
export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: null,
  }),

  getters: {
    isAuthenticated: (state) => state.token !== null,
  },

  actions: {
    async login(username, password) {
      const data = await apiFetch('/api/auth/login', {
        method: 'POST',
        body: { username, password },
      })
      this.token = data.access_token
    },

    logout() {
      this.token = null
    },
  },
})
