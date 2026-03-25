<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  seasonNumber: number
  lastPlayed: string | null
  monthThreshold: number
}>()

const status = computed(() => {
  if (!props.lastPlayed) return 'unmatched'
  const played = new Date(props.lastPlayed)
  // Match backend: threshold * 30 days
  const cutoff = new Date(Date.now() - props.monthThreshold * 30 * 24 * 60 * 60 * 1000)
  return played >= cutoff ? 'recent' : 'old'
})

const colorMap = {
  recent: 'bg-emerald-400/70 dark:bg-emerald-400/60',
  old: 'bg-rose-400/70 dark:bg-rose-400/60',
  unmatched: 'bg-surface-300 dark:bg-surface-600',
}
</script>

<template>
  <span
    class="block h-5 min-w-0.5 rounded-sm cursor-help flex-1"
    :class="colorMap[status]"
    :title="`S${String(seasonNumber).padStart(2, '0')} — ${lastPlayed ? `last played ${lastPlayed.split(' ')[0]}` : 'no data'}`"
  />
</template>
