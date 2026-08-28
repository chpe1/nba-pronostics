<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/apiClient'

const authStore = useAuthStore()
const router = useRouter()

const username = ref('')
const password = ref('')
const errorMessage = ref('')
const isSubmitting = ref(false)

async function handleSubmit() {
  isSubmitting.value = true
  errorMessage.value = ''
  try {
    await authStore.login(username.value, password.value)
    router.push({ name: 'admin-imports' })
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      errorMessage.value = 'Identifiants invalides.'
    } else if (error instanceof ApiError && error.status === 429) {
      // Verrou anti-brute-force (app/services/login_lockout.py) : le
      // message du backend inclut déjà le délai d'attente restant.
      errorMessage.value = error.message
    } else {
      errorMessage.value = 'Connexion impossible pour le moment.'
    }
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <section class="mx-auto max-w-sm px-4 py-12">
    <h1 class="mb-6 text-xl font-semibold text-gray-900">Connexion admin</h1>

    <form class="space-y-4" @submit.prevent="handleSubmit">
      <div>
        <label for="username" class="mb-1 block text-sm font-medium text-gray-700">Identifiant</label>
        <input
          id="username"
          v-model="username"
          type="text"
          autocomplete="username"
          required
          class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
      </div>

      <div>
        <label for="password" class="mb-1 block text-sm font-medium text-gray-700">Mot de passe</label>
        <input
          id="password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
          class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
      </div>

      <p v-if="errorMessage" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
        {{ errorMessage }}
      </p>

      <button
        type="submit"
        class="w-full rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        :disabled="isSubmitting"
      >
        {{ isSubmitting ? 'Connexion…' : 'Se connecter' }}
      </button>
    </form>
  </section>
</template>
