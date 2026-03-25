<script setup lang="ts">
import PrimeProgressBar from 'primevue/progressbar'

defineProps<{
  percent: number
  step: string
  stepIndex?: number
  totalSteps?: number
}>()
</script>

<template>
  <div class="space-y-1.5">
    <div class="flex justify-between text-sm text-surface-500">
      <span>
        {{ step.split(':')[0] }}
        <span v-if="step.includes(':')" class="text-surface-400">: {{ step.split(':').slice(1).join(':').trim() }}</span>
      </span>
      <span class="tabular-nums">
        {{ Math.round(percent) }}%
        <span v-if="stepIndex && totalSteps" class="text-surface-400 ml-1.5">({{ stepIndex }}/{{ totalSteps }})</span>
      </span>
    </div>
    <PrimeProgressBar :value="Math.min(Math.round(percent), 100)" :showValue="false" style="height: 20px" class="striped-progress" />
  </div>
</template>

<style scoped>
.striped-progress :deep([data-pc-section="value"]) {
  background-image: linear-gradient(
    45deg,
    rgba(255, 255, 255, 0.15) 25%,
    transparent 25%,
    transparent 50%,
    rgba(255, 255, 255, 0.15) 50%,
    rgba(255, 255, 255, 0.15) 75%,
    transparent 75%,
    transparent
  );
  background-size: 28px 28px;
  animation: stripe-move 1s linear infinite;
}

@keyframes stripe-move {
  from { background-position: 28px 0; }
  to { background-position: 0 0; }
}
</style>
