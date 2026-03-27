<script setup lang="ts">
import type { Summary, CategoryStats, MatchingStats } from '../types/api'

const props = defineProps<{
  summary: Summary
}>()

/**
 * Format number with thousands separators.
 */
function n(val: number): string {
  return val.toLocaleString()
}

/**
 * Display a size string, or '-' if empty.
 */
function fmt(val: string): string {
  return val || '-'
}

/**
 * Table row model. Used to build rows dynamically.
 * Movies, shows, seasons, and sizes are optional to handle separator rows.
 */
type Row = {
  label: string
  movies?: string; shows?: string; seasons?: string
  movieSize?: string; seriesSize?: string; seriesSizeGreedy?: string
  cls: string;         // Tailwind color class for the row
  sep?: boolean        // If true, render as separator line instead of data row
}

/**
 * Create a data row from a CategoryStats object (e.g. "Recently watched", "Never watched").
 * Formats counts and sizes for display. showSeasons=false hides season count for never-watched.
 */
function catRow(label: string, cat: CategoryStats, cls: string, showSeasons = true): Row {
  return {
    label,
    movies: n(cat.movieCount),
    shows: n(cat.showsCount),
    seasons: showSeasons ? n(cat.seasonsCount) : '',
    movieSize: fmt(cat.movieSizeFmt),
    seriesSize: fmt(cat.seriesSizeFmt),
    seriesSizeGreedy: fmt(cat.seriesSizeGreedyFmt),
    cls,
  }
}

/**
 * Create a data row from MatchingStats counters (e.g. "Matched", "Ambiguous").
 * Takes property keys (movieKey, showsKey, seasonsKey) to pull specific counts.
 */
function matchRow(label: string, movieKey: keyof MatchingStats, showsKey: keyof MatchingStats, seasonsKey: keyof MatchingStats, cls: string): Row {
  return {
    label,
    movies: n(props.summary.matching[movieKey] as number),
    shows: n(props.summary.matching[showsKey] as number),
    seasons: n(props.summary.matching[seasonsKey] as number),
    cls,
  }
}

/**
 * Summary table structure: watch categories, then library totals, then matching quality metrics.
 * catRow() pulls counts/sizes from each category. matchRow() pulls matching stats.
 * Separator rows ({ sep: true }) are rendered as a border line in the template.
 */
const rows: Row[] = [
  // Watch categories (what was actually watched)
  catRow('Recently watched', props.summary.recent, 'text-green-500 dark:text-green-400'),
  catRow('Not recently watched', props.summary.old, 'text-red-500 dark:text-red-400'),
  catRow('Never watched', props.summary.neverWatched, 'text-purple-500 dark:text-purple-400', false),
  catRow('New (unwatched)', props.summary.neverNew, 'text-cyan-500 dark:text-cyan-400', false),
  { label: '', sep: true, cls: '' },
  // Overall library and kept items
  catRow('Library total', props.summary.library, 'text-surface-400', false),
  catRow('Kept', props.summary.kept, 'text-yellow-500 dark:text-yellow-400'),
  { label: '', sep: true, cls: '' },
  // Matching quality (how well items were matched to the library)
  matchRow('Matched', 'matchedMovieCount', 'matchedShowsCount', 'matchedSeasonsCount', 'text-green-500 dark:text-green-400'),
  matchRow('Ambiguous', 'ambiguousMovieCount', 'ambiguousShowsCount', 'ambiguousSeasonsCount', 'text-yellow-500 dark:text-yellow-400'),
  {
    label: 'Collision',
    movies: n(props.summary.matching.collisionMovieCount),
    seasons: n(props.summary.matching.collisionSeasonCount),
    cls: 'text-orange-500 dark:text-orange-400',
  },
  matchRow('Unmatched', 'unmatchedMovieCount', 'unmatchedShowsCount', 'unmatchedSeasonsCount', 'text-red-500 dark:text-red-400'),
]
</script>

<template>
  <div class="card overflow-x-auto">
    <div class="px-4 py-3">
      <h2 class="text-sm font-semibold text-surface-500 uppercase tracking-wide">Summary</h2>
    </div>
    <table class="w-full text-xs sm:text-sm">
      <thead>
        <tr class="text-left text-xs font-medium text-surface-400 uppercase tracking-wider">
          <th class="px-2 sm:px-4 py-2"></th>
          <th class="px-2 sm:px-4 py-2 text-right">Movies</th>
          <th class="px-2 sm:px-4 py-2 text-right">Shows</th>
          <th class="px-2 sm:px-4 py-2 text-right">Seasons</th>
          <th class="px-2 sm:px-4 py-2 text-right">Movie Size</th>
          <th class="px-2 sm:px-4 py-2 text-right">Series Size</th>
          <th class="px-2 sm:px-4 py-2 text-right">Series Size (Greedy)</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="(row, i) in rows" :key="i">
          <tr v-if="row.sep" class="h-px">
            <td colspan="7" class="p-0">
              <div class="border-t border-gray-700 dark:border-gray-600"></div>
            </td>
          </tr>
          <tr v-else>
            <td class="px-2 sm:px-4 py-2 text-surface-300 dark:text-surface-500 font-medium whitespace-nowrap">{{ row.label }}</td>
            <td class="px-2 sm:px-4 py-2 text-right tabular-nums" :class="row.cls">{{ row.movies ?? '' }}</td>
            <td class="px-2 sm:px-4 py-2 text-right tabular-nums" :class="row.cls">{{ row.shows ?? '' }}</td>
            <td class="px-2 sm:px-4 py-2 text-right tabular-nums" :class="row.cls">{{ row.seasons ?? '' }}</td>
            <td class="px-2 sm:px-4 py-2 text-right tabular-nums whitespace-nowrap" :class="row.cls">{{ row.movieSize ?? '' }}</td>
            <td class="px-2 sm:px-4 py-2 text-right tabular-nums whitespace-nowrap" :class="row.cls">{{ row.seriesSize ?? '' }}</td>
            <td class="px-2 sm:px-4 py-2 text-right tabular-nums whitespace-nowrap" :class="row.cls">{{ row.seriesSizeGreedy ?? '' }}</td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>
