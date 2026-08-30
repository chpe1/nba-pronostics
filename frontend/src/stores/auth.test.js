import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/services/apiClient', () => ({
  apiFetch: vi.fn(),
}))

import { apiFetch } from '@/services/apiClient'
import { useAuthStore } from './auth'

const STORAGE_KEY = 'nba-pronostics-token'

// L'environnement de test tourne en Node (vite.config.js), pas jsdom -- pas
// de localStorage global par défaut, contrairement à un vrai navigateur.
function stubLocalStorage(initial = {}) {
  const backing = { ...initial }
  const mock = {
    getItem: vi.fn((key) => (key in backing ? backing[key] : null)),
    setItem: vi.fn((key, value) => {
      backing[key] = value
    }),
    removeItem: vi.fn((key) => {
      delete backing[key]
    }),
  }
  vi.stubGlobal('localStorage', mock)
  return mock
}

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.unstubAllGlobals()
    apiFetch.mockReset()
  })

  it('réhydrate le jeton depuis localStorage à la création du store', () => {
    stubLocalStorage({ [STORAGE_KEY]: 'stored-token' })

    const store = useAuthStore()

    expect(store.token).toBe('stored-token')
    expect(store.isAuthenticated).toBe(true)
  })

  it("démarre non authentifié quand aucun jeton n'est stocké", () => {
    stubLocalStorage()

    const store = useAuthStore()

    expect(store.token).toBeNull()
    expect(store.isAuthenticated).toBe(false)
  })

  it('persiste le jeton dans localStorage après une connexion réussie', async () => {
    const storage = stubLocalStorage()
    apiFetch.mockResolvedValue({ access_token: 'new-token' })
    const store = useAuthStore()

    await store.login('admin', 'secret')

    expect(store.token).toBe('new-token')
    expect(storage.setItem).toHaveBeenCalledWith(STORAGE_KEY, 'new-token')
  })

  it('vide le jeton (état + localStorage) à la déconnexion', () => {
    const storage = stubLocalStorage({ [STORAGE_KEY]: 'stored-token' })
    const store = useAuthStore()

    store.logout()

    expect(store.token).toBeNull()
    expect(store.isAuthenticated).toBe(false)
    expect(storage.removeItem).toHaveBeenCalledWith(STORAGE_KEY)
  })
})
