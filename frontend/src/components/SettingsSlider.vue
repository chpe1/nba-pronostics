<script setup>
import InfoTooltip from '@/components/InfoTooltip.vue'

const props = defineProps({
  label: { type: String, required: true },
  min: { type: Number, default: 0 },
  max: { type: Number, default: 10 },
  step: { type: Number, default: 0.1 },
  help: { type: String, default: '' },
})

const value = defineModel({ type: Number, required: true })
</script>

<template>
  <div>
    <div class="mb-1 flex items-center justify-between text-sm">
      <label class="flex items-center font-medium text-gray-700">
        {{ props.label }}
        <InfoTooltip v-if="props.help" :text="props.help" />
      </label>
      <span class="tabular-nums text-gray-500">{{ value }}</span>
    </div>
    <input
      v-model.number="value"
      type="range"
      :min="props.min"
      :max="props.max"
      :step="props.step"
      class="w-full"
    />
  </div>
</template>
