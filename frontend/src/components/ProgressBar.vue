<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import PrimeProgressBar from 'primevue/progressbar'

defineProps<{
  percent: number
  step: string         // e.g. "Matching movies: 42/100" or "Matching movies"
  stepIndex?: number   // Current step number (e.g., 3 of 8)
  totalSteps?: number  // Total steps in the pipeline (e.g., 8)
}>()

// Whimsical status messages that cycle every 3s for entertainment during long runs
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
  'flubbergusting...',
  'boondoggling...'
]

// Shuffle the array each time the component mounts (each analysis run)
function shuffle<T>(arr: T[]): T[] {
  const a = [...arr]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

let shuffled = shuffle(vibes)
const currentVibe = ref(shuffled[0])
let vibeIndex = 0
let timer: ReturnType<typeof setInterval>

onMounted(() => {
  shuffled = shuffle(vibes)
  vibeIndex = 0
  currentVibe.value = shuffled[0]
  timer = setInterval(() => {
    vibeIndex = (vibeIndex + 1) % shuffled.length
    currentVibe.value = shuffled[vibeIndex]
  }, 3000)
})

onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="space-y-1.5">
    <div class="flex flex-wrap justify-between text-xs sm:text-sm text-surface-500 gap-x-2">
      <span class="min-w-0 truncate">
        <!-- Split step name on first ':' to separate main step from subtext (e.g. "Matching movies" from "42/100") -->
        {{ step.split(':')[0] }}
        <span v-if="step.includes(':')" class="text-surface-400">: {{ step.split(':').slice(1).join(':').trim() }}</span>
      </span>
      <span class="tabular-nums shrink-0">
        {{ Math.round(percent) }}%
        <!-- Show pipeline progress (e.g. "3/8") only if both step index and total are provided -->
        <span v-if="stepIndex && totalSteps" class="text-surface-400 ml-1.5">({{ stepIndex }}/{{ totalSteps }})</span>
        <!-- Whimsical message that cycles periodically -->
        <span class="text-surface-400 ml-2 italic font-normal">{{ currentVibe }}</span>
      </span>
    </div>
    <!-- Animated striped progress bar (capped at 100%) -->
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
