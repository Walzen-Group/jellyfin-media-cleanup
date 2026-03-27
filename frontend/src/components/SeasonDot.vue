<script setup lang="ts">
/**
 * SeasonDot: compact visual indicator for a single season's watch status.
 * Used in the season overview row of the series table. Color indicates status,
 * and a tooltip shows season number and last played date on hover.
 */

import type { MediaStatus } from '../types/api'

defineProps<{
  seasonNumber: number
  lastPlayed: string | null    // ISO date string or null for never-watched
  status: MediaStatus           // Watch status: recent, old, kept, etc.
  inactive?: boolean            // When true, dims the dot without affecting the tooltip
}>()

/**
 * Color mapping for each status. Used for the dot's background.
 * Matches the color scheme in the main tables for visual consistency.
 */
const colorMap: Record<string, string> = {
  recent: 'bg-emerald-400/70 dark:bg-emerald-400/60',
  old: 'bg-rose-400/70 dark:bg-rose-400/60',
  kept: 'bg-amber-400/70 dark:bg-amber-400/60',
  auto_keep: 'bg-yellow-400/70 dark:bg-yellow-400/60',
  mixed: 'bg-blue-400/70 dark:bg-blue-400/60',
  unmatched: 'bg-surface-300 dark:bg-surface-600',
  never: 'bg-purple-400/70 dark:bg-purple-400/60',
  never_new: 'bg-cyan-400/70 dark:bg-cyan-400/60',
  collision: 'bg-orange-400/70 dark:bg-orange-400/60',
}
</script>

<template>
  <!-- Wrapper: positions the tooltip. No opacity applied here so the tooltip is never dimmed. -->
  <span class="season-dot relative block h-5 min-w-0.5 rounded-sm cursor-default flex-1">
    <!-- Inner color element: opacity is applied here so it doesn't affect the tooltip child -->
    <span
      class="absolute inset-0 rounded-sm"
      :class="[colorMap[status] ?? colorMap.unmatched, inactive ? 'opacity-20' : '']"
    />
    <!-- Tooltip: shows season number and last-played date (or "no data" if never watched) -->
    <span class="tooltip">S{{ String(seasonNumber).padStart(2, '0') }} · {{ lastPlayed ? lastPlayed.split(' ')[0] : 'no data' }}</span>
  </span>
</template>

<style scoped>
/* Tooltip positioned above the dot, centered horizontally. Hidden by default. */
.season-dot .tooltip {
  visibility: hidden;
  opacity: 0;
  position: absolute;
  bottom: calc(100% + 6px);    /* 6px gap above the dot */
  left: 50%;
  transform: translateX(-50%); /* Center horizontally */
  white-space: nowrap;
  font-size: 13px;
  padding: 5px 10px;
  border-radius: 4px;
  background: var(--p-surface-900);  /* Light mode: dark background */
  color: var(--p-surface-0);
  pointer-events: none;        /* Tooltip doesn't interfere with interactions */
  z-index: 50;                 /* Above other elements */
  transition: opacity 0.1s;    /* Smooth fade in/out */
}
/* Dark mode: invert tooltip colors */
.dark .season-dot .tooltip {
  background: var(--p-surface-100);
  color: var(--p-surface-900);
}
/* Show tooltip on hover */
.season-dot:hover .tooltip {
  visibility: visible;
  opacity: 1;
}
</style>
