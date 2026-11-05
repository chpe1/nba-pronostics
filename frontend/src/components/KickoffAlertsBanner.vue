<script setup>
import { formatLocalTime } from '@/utils/oddsFetchFormat'

// L'API des cotes annonce un coup d'envoi PLUS TÔT que notre calendrier. Rien n'est corrigé ici (ni le calendrier
// ni la protection des pronostics) : l'alerte informe, l'utilisateur décide.
defineProps({ alerts: { type: Array, default: () => [] } })
</script>

<template>
  <div
    v-if="alerts.length"
    role="alert"
    data-testid="kickoff-alerts"
    class="space-y-1 rounded-lg border border-border bg-surface-sunken px-3 py-2 text-sm text-text"
  >
    <p v-for="alert in alerts" :key="alert.game_id" data-testid="kickoff-alert">
      <strong>{{ alert.label }}</strong> : l'API annonce le coup d'envoi à {{ formatLocalTime(alert.api_start) }},
      notre calendrier à {{ formatLocalTime(alert.our_start) }} (heure de ce navigateur) —
      {{ alert.minutes_earlier }} min plus tôt. Rien n'est corrigé : à vérifier sur l'écran Matchs.
    </p>
  </div>
</template>
