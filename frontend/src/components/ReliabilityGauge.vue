<script setup>
defineProps({
  reliability: {
    type: String,
    required: true,
  },
})

const STYLES = {
  faible: 'bg-neutral/15 text-neutral',
  moyenne: 'bg-warning/15 text-warning',
  forte: 'bg-success/15 text-success',
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
