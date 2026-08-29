<script setup>
import { ref, onMounted } from 'vue'
import { apiFetch, ApiError } from '@/services/apiClient'
import CsvUploadForm from '@/components/CsvUploadForm.vue'
import CsvTemplatesCard from '@/components/CsvTemplatesCard.vue'
import ImportHistoryTable from '@/components/ImportHistoryTable.vue'

const history = ref([])
const errorMessage = ref('')

async function loadHistory() {
  errorMessage.value = ''
  try {
    history.value = await apiFetch('/api/imports/history')
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Impossible de charger l'historique."
  }
}

onMounted(loadHistory)
</script>

<template>
  <section class="mx-auto max-w-2xl space-y-4 px-4 py-6">
    <h1 class="text-xl font-semibold text-text">Import des statistiques</h1>

    <p v-if="errorMessage" class="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger-text">
      {{ errorMessage }}
    </p>

    <CsvTemplatesCard />
    <CsvUploadForm @imported="loadHistory" />
    <ImportHistoryTable :history="history" />
  </section>
</template>
