<script setup>
defineProps({
  reliability: {
    type: String,
    required: true,
  },
})

const STYLES = {
  faible: 'bg-gray-200 text-gray-700',
  moyenne: 'bg-amber-100 text-amber-800',
  forte: 'bg-emerald-100 text-emerald-800',
}

const LABELS = {
  faible: 'Fiabilité faible',
  moyenne: 'Fiabilité moyenne',
  forte: 'Fiabilité forte',
}
</script>

<template>
  <span
    class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium"
    :class="STYLES[reliability] ?? STYLES.faible"
  >
    {{ LABELS[reliability] ?? reliability }}
  </span>
</template>
