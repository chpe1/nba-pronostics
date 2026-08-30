import { defineStore } from 'pinia'
import { apiFetch } from '@/services/apiClient'

// Jeton persisté en localStorage (décision du 2026-08-30, voir CLAUDE.md
// "Décisions d'architecture") : survit à un F5 et à un redémarrage du
// navigateur -- borné de toute façon par l'expiration du JWT côté serveur
// (ACCESS_TOKEN_EXPIRE_MINUTES, 8h par défaut, app/core/security.py), donc
// pas de session éternelle même si le stockage, lui, ne l'efface jamais.
const STORAGE_KEY = 'nba-pronostics-token'

function readStoredToken() {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    // Stockage indisponible (navigation privée, quota) : pas de jeton à
    // réhydrater, l'utilisateur devra simplement se reconnecter.
    return null
  }
}

function persistToken(token) {
  try {
    if (token) {
      localStorage.setItem(STORAGE_KEY, token)
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  } catch {
    // Même politique que stores/theme.js : le jeton reste appliqué pour la
    // session en cours, simplement pas persisté pour la prochaine visite.
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    // Lecture SYNCHRONE au moment de la création du store -- même patron que
    // stores/theme.js (document.documentElement.getAttribute(...) dans sa
    // factory state). Aucune fenêtre de course avec le garde de route
    // possible : le garde ne peut s'exécuter qu'après la résolution de la
    // navigation initiale, elle-même postérieure au montage de l'app, donc
    // strictement après que cette factory ait déjà tourné (voir main.js).
    token: readStoredToken(),
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
      persistToken(this.token)
    },

    logout() {
      this.token = null
      persistToken(null)
    },
  },
})
