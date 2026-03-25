<script setup lang="ts">
const props = defineProps<{
  summary: Record<string, unknown>
}>()

function n(key: string): string {
  const v = props.summary[key]
  if (typeof v === 'number') return v.toLocaleString()
  return String(v ?? '')
}

function fmt(key: string): string {
  return String(props.summary[key] ?? '-')
}

type Row = { label: string; movies?: string; shows?: string; seasons?: string; size?: string; cls: string; sep?: boolean }

const rows: Row[] = [
  { label: 'Recently watched', movies: 'recent_movie_count', shows: 'recent_shows_count', seasons: 'recent_seasons_count', size: 'recent_size_fmt', cls: 'text-green-500 dark:text-green-400' },
  { label: 'Not recently watched', movies: 'old_movie_count', shows: 'old_shows_count', seasons: 'old_seasons_count', size: 'old_size_fmt', cls: 'text-red-500 dark:text-red-400' },
  { label: 'Never watched', movies: 'never_watched_movie_count', shows: 'never_watched_series_count', size: 'never_watched_size_fmt', cls: 'text-surface-400' },
  { label: '', sep: true, cls: '' },
  { label: 'Library total', movies: 'library_movie_count', shows: 'library_series_count', size: 'lib_size_fmt', cls: 'text-surface-400' },
  { label: 'Kept', movies: 'kept_movie_count', shows: 'kept_shows_count', seasons: 'kept_seasons_count', size: 'kept_size_fmt', cls: 'text-yellow-500 dark:text-yellow-400' },
  { label: '', sep: true, cls: '' },
  { label: 'Matched', movies: 'matched_movie_count', shows: 'matched_shows_count', seasons: 'matched_seasons_count', cls: 'text-green-500 dark:text-green-400' },
  { label: 'Ambiguous', movies: 'ambiguous_movie_count', shows: 'ambiguous_shows_count', seasons: 'ambiguous_seasons_count', cls: 'text-yellow-500 dark:text-yellow-400' },
  { label: 'Unmatched', movies: 'unmatched_movie_count', shows: 'unmatched_shows_count', seasons: 'unmatched_seasons_count', cls: 'text-red-500 dark:text-red-400' },
]
</script>

<template>
  <div class="card overflow-hidden">
    <div class="px-4 py-3">
      <h2 class="text-sm font-semibold text-surface-500 uppercase tracking-wide">Summary</h2>
    </div>
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-xs font-medium text-surface-400 uppercase tracking-wider">
          <th class="px-4 py-2"></th>
          <th class="px-4 py-2 text-right">Movies</th>
          <th class="px-4 py-2 text-right">Shows</th>
          <th class="px-4 py-2 text-right">Seasons</th>
          <th class="px-4 py-2 text-right">Size</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="(row, i) in rows" :key="i">
          <tr v-if="row.sep" class="h-px">
            <td colspan="5" class="p-0">
              <div class="border-t border-surface-100 dark:border-surface-800"></div>
            </td>
          </tr>
          <tr v-else>
            <td class="px-4 py-2 text-surface-300 dark:text-surface-500 font-medium">{{ row.label }}</td>
            <td class="px-4 py-2 text-right tabular-nums" :class="row.cls">{{ row.movies ? n(row.movies) : '' }}</td>
            <td class="px-4 py-2 text-right tabular-nums" :class="row.cls">{{ row.shows ? n(row.shows) : '' }}</td>
            <td class="px-4 py-2 text-right tabular-nums" :class="row.cls">{{ row.seasons ? n(row.seasons) : '' }}</td>
            <td class="px-4 py-2 text-right tabular-nums" :class="row.cls">{{ row.size ? fmt(row.size) : '' }}</td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>
