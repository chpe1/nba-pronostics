<script setup>
defineProps({
  history: {
    type: Array,
    required: true,
  },
})

const STATUS_STYLES = {
  success: 'bg-success/15 text-success',
  partial: 'bg-warning/15 text-warning',
  error: 'bg-danger/15 text-danger-text',
}

function formatDate(value) {
  return new Date(value).toLocaleString('fr-FR')
}
</script>

<template>
  <div class="rounded-xl border border-border bg-surface p-4">
    <h2 class="mb-3 text-sm font-semibold text-text">Historique des imports</h2>

    <p v-if="history.length === 0" class="text-sm text-text-secondary">Aucun import pour l'instant.</p>

    <table v-else class="w-full border-collapse text-left text-sm">
      <thead>
        <tr class="text-xs text-text-secondary">
          <th class="border-b p-2 font-medium">Date</th>
          <th class="border-b p-2 font-medium">Fichier</th>
          <th class="border-b p-2 font-medium">Type</th>
          <th class="border-b p-2 font-medium">Saison</th>
          <th class="border-b p-2 font-medium">Lignes</th>
          <th class="border-b p-2 font-medium">Statut</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="entry in history" :key="entry.id">
          <td class="border-b p-2">{{ formatDate(entry.created_at) }}</td>
          <td class="border-b p-2">{{ entry.filename }}</td>
          <td class="border-b p-2">{{ entry.import_type }}</td>
          <td class="border-b p-2">{{ entry.season ?? 'courante' }}</td>
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
