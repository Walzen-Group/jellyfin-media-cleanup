<script setup lang="ts">
/**
 * Compact summary bar for filtered results.
 * Displays counts and total size in a single horizontal line.
 */

import type { FilteredSummary } from '../types/api'

defineProps<{
  summary: FilteredSummary
}>()
</script>

<template>
  <div class="card px-3 sm:px-5 py-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs sm:text-sm text-surface-500">
    <span class="font-medium text-surface-700 dark:text-surface-200">{{ summary.movieCount.toLocaleString() }}</span>
    / {{ summary.totalMovieCount.toLocaleString() }} movies
    <span class="text-surface-300">&middot;</span>
    <span class="font-medium text-surface-700 dark:text-surface-200">{{ summary.seriesCount.toLocaleString() }}</span>
    / {{ summary.totalSeriesCount.toLocaleString() }} series
    <span class="text-surface-300">&middot;</span>
    <span class="font-medium text-surface-700 dark:text-surface-200">{{ summary.seasonCount.toLocaleString() }}</span>
    / {{ summary.totalSeasonCount.toLocaleString() }} seasons
    <span class="text-surface-300">&middot;</span>
    <span class="font-medium text-surface-700 dark:text-surface-200">{{ summary.totalSizeFmt }}</span>
    / {{ summary.totalLibrarySizeFmt }}
  </div>
</template>
