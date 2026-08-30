import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './style.css'
import App from './App.vue'
import router from './router'
import { configureApiClient } from './services/apiClient'
import { useAuthStore } from './stores/auth'

const app = createApp(App)

app.use(createPinia())
app.use(router)

const authStore = useAuthStore()
configureApiClient({
  getToken: () => authStore.token,
  // 401 sur une requête qui portait un jeton = session expirée/invalide
  // (jamais un échec de connexion, voir apiClient.js) -- vide le jeton et
  // redirige vers /login avec un motif dédié, distinct des identifiants
  // invalides/du verrou anti-bruteforce (voir LoginView.vue).
  onUnauthorized: () => {
    authStore.logout()
    router.push({ name: 'login', query: { reason: 'expired' } })
  },
})

app.mount('#app')
