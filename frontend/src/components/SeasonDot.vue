<script setup lang="ts">
import type { MediaStatus } from '../types/api'

defineProps<{
  seasonNumber: number
  lastPlayed: string | null
  status: MediaStatus
}>()

const colorMap: Record<string, string> = {
  recent: 'bg-emerald-400/70 dark:bg-emerald-400/60',
  old: 'bg-rose-400/70 dark:bg-rose-400/60',
  kept: 'bg-amber-400/70 dark:bg-amber-400/60',
  mixed: 'bg-blue-400/70 dark:bg-blue-400/60',
  unmatched: 'bg-surface-300 dark:bg-surface-600',
  never: 'bg-purple-400/70 dark:bg-purple-400/60',
  never_new: 'bg-cyan-400/70 dark:bg-cyan-400/60',
  collision: 'bg-fuchsia-400/70 dark:bg-fuchsia-400/60',
}
</script>

<template>
  <span class="season-dot relative block h-5 min-w-0.5 rounded-sm cursor-default flex-1" :class="colorMap[status] ?? colorMap.unmatched">
    <span class="tooltip">S{{ String(seasonNumber).padStart(2, '0') }} · {{ lastPlayed ? lastPlayed.split(' ')[0] : 'no data' }}</span>
  </span>
</template>

<style scoped>
.season-dot .tooltip {
  visibility: hidden;
  opacity: 0;
  position: absolute;
  bottom: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  font-size: 13px;
  padding: 5px 10px;
  border-radius: 4px;
  background: var(--p-surface-900);
  color: var(--p-surface-0);
  pointer-events: none;
  z-index: 50;
  transition: opacity 0.1s;
}
.dark .season-dot .tooltip {
  background: var(--p-surface-100);
  color: var(--p-surface-900);
}
.season-dot:hover .tooltip {
  visibility: visible;
  opacity: 1;
}
</style>
