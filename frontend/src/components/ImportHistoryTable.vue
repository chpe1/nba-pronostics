<script setup>
defineProps({
  history: {
    type: Array,
    required: true,
  },
})

const STATUS_STYLES = {
  success: 'bg-emerald-100 text-emerald-800',
  partial: 'bg-amber-100 text-amber-800',
  error: 'bg-red-100 text-red-800',
}

function formatDate(value) {
  return new Date(value).toLocaleString('fr-FR')
}
</script>

<template>
  <div class="rounded-xl border border-gray-200 bg-white p-4">
    <h2 class="mb-3 text-sm font-semibold text-gray-900">Historique des imports</h2>

    <p v-if="history.length === 0" class="text-sm text-gray-500">Aucun import pour l'instant.</p>

    <table v-else class="w-full border-collapse text-left text-sm">
      <thead>
        <tr class="text-xs text-gray-500">
          <th class="border-b p-2 font-medium">Date</th>
          <th class="border-b p-2 font-medium">Fichier</th>
          <th class="border-b p-2 font-medium">Type</th>
          <th class="border-b p-2 font-medium">Lignes</th>
          <th class="border-b p-2 font-medium">Statut</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="entry in history" :key="entry.id">
          <td class="border-b p-2">{{ formatDate(entry.created_at) }}</td>
          <td class="border-b p-2">{{ entry.filename }}</td>
          <td class="border-b p-2">{{ entry.import_type }}</td>
          <td class="border-b p-2">{{ entry.row_count }} ({{ entry.error_count }} erreur(s))</td>
          <td class="border-b p-2">
            <span class="rounded-full px-2 py-0.5 text-xs font-medium" :class="STATUS_STYLES[entry.status]">
              {{ entry.status }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
