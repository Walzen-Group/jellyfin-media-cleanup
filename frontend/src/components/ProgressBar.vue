<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import PrimeProgressBar from 'primevue/progressbar'

defineProps<{
  percent: number
  step: string
  stepIndex?: number
  totalSteps?: number
}>()

const vibes = [
  'cringlebingling...',
  'defragulating...',
  'hooting...',
  'wrangling...',
  'snorkelizing...',
  'discombobulating...',
  'fluxinating...',
  'schmoozing...',
  'murkyflurking...',
  'perambulating...',
  'razzledazzling...',
  'gizoogling...',
  'cradanceparancing...',
  'boingzoinging...',
  'seesawing...',
  'humpteedumpting...',
]

const currentVibe = ref(vibes[0])
let vibeIndex = 0
let timer: ReturnType<typeof setInterval>

onMounted(() => {
  timer = setInterval(() => {
    vibeIndex = (vibeIndex + 1) % vibes.length
    currentVibe.value = vibes[vibeIndex]
  }, 3000)
})

onUnmounted(() => clearInterval(timer))
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
        <span class="text-surface-400 ml-2 italic font-normal">{{ currentVibe }}</span>
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
