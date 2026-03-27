<script setup lang="ts">
/**
 * Step 3 of the wizard: deletion preview.
 * Shows exactly which Radarr movies and Sonarr series/seasons would be affected.
 * Calls store.prepareRunPlan() which hits the backend prepare endpoint.
 * Users can search across all tables and deselect individual items via checkboxes.
 */

import { ref, computed, watch, onMounted } from 'vue'
import { useJobStore } from '../stores/jobStore'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Panel from 'primevue/panel'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import type { MovieDeletion, FullSeriesDeletion, SeasonCleanup } from '../types/api'

const store = useJobStore()

/** Re-derive the filter params from filteredResult categories on the store. */
const canPrepare = computed(() => !!store.filteredResult)

/** Search query applied across all three tables */
const searchQuery = ref('')

/** Selected (checked) items per table. Initialized to all items when runPlan loads. */
const selectedMovies = ref<MovieDeletion[]>([])
const selectedFullSeries = ref<FullSeriesDeletion[]>([])
const selectedSeasonCleanups = ref<SeasonCleanup[]>([])

/** When runPlan loads or changes, select all items by default */
watch(() => store.runPlan, (plan) => {
  if (plan) {
    selectedMovies.value = [...plan.movies]
    selectedFullSeries.value = [...plan.fullSeries]
    selectedSeasonCleanups.value = [...plan.seasonCleanups]
  }
}, { immediate: true })

/** Human-readable labels for the filter settings from step 2 */
const categoryLabels: Record<string, string> = {
  old: 'Not recently watched',
  never: 'Never watched',
  never_new: 'New (unwatched)',
}
const categoryDots: Record<string, string> = {
  old: 'bg-rose-400/70 dark:bg-rose-400/60',
  never: 'bg-purple-400/70 dark:bg-purple-400/60',
  never_new: 'bg-cyan-400/70 dark:bg-cyan-400/60',
}
const mediaTypeLabels: Record<string, string> = {
  all: 'All media',
  movies: 'Movies only',
  series: 'Series only',
}

const lowerSearch = computed(() => searchQuery.value.toLowerCase().trim())

const visibleMovies = computed(() => {
  if (!store.runPlan) return []
  if (!lowerSearch.value) return store.runPlan.movies
  return store.runPlan.movies.filter(m =>
    m.title.toLowerCase().includes(lowerSearch.value)
  )
})

const visibleFullSeries = computed(() => {
  if (!store.runPlan) return []
  if (!lowerSearch.value) return store.runPlan.fullSeries
  return store.runPlan.fullSeries.filter(s =>
    s.title.toLowerCase().includes(lowerSearch.value)
  )
})

const visibleSeasonCleanups = computed(() => {
  if (!store.runPlan) return []
  if (!lowerSearch.value) return store.runPlan.seasonCleanups
  return store.runPlan.seasonCleanups.filter(s =>
    s.title.toLowerCase().includes(lowerSearch.value)
  )
})

const hasResults = computed(() => {
  const rp = store.runPlan
  if (!rp) return false
  return rp.movies.length > 0 || rp.fullSeries.length > 0 || rp.seasonCleanups.length > 0
})

const isEmpty = computed(() => {
  const rp = store.runPlan
  if (!rp) return false
  return rp.movies.length === 0 && rp.fullSeries.length === 0 && rp.seasonCleanups.length === 0
})

/** Summary that reflects only the currently selected (checked) items */
const selectionSummary = computed(() => {
  const movieSize = selectedMovies.value.reduce((sum, m) => sum + m.sizeBytes, 0)
  const seriesSize = selectedFullSeries.value.reduce((sum, s) => sum + s.sizeBytes, 0)
  const seasonSize = selectedSeasonCleanups.value.reduce((sum, s) => sum + s.totalSizeBytes, 0)
  const totalSize = movieSize + seriesSize + seasonSize
  return {
    movieCount: selectedMovies.value.length,
    fullSeriesCount: selectedFullSeries.value.length,
    seasonCleanupCount: selectedSeasonCleanups.value.length,
    totalSizeFmt: formatSize(totalSize),
  }
})

function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  const value = bytes / Math.pow(1024, i)
  return `${value.toFixed(i > 0 ? 1 : 0)} ${units[i]}`
}

/** Collapsed state for each toggleable Panel */
const fullSeriesCollapsed = ref(false)
const seasonCleanupsCollapsed = ref(false)
const moviesCollapsed = ref(false)

/**
 * Per-panel PassThrough objects defined in script setup (not in template) so
 * that the ref objects are accessed as Ref<boolean> with .value — in the template
 * Vue auto-unwraps refs to plain booleans, making .value inaccessible.
 *
 * Header onClick toggles collapsed state. stopPropagation on the toggle button
 * prevents the click from bubbling up to the header handler after PrimeVue's
 * own toggle has already fired, avoiding a double-toggle.
 */
const _toggleButtonPt = { onClick: (e: Event) => e.stopPropagation() }
const fullSeriesPt = {
  header: { onClick: () => { fullSeriesCollapsed.value = !fullSeriesCollapsed.value }, class: 'cursor-pointer select-none' },
  togglebutton: _toggleButtonPt,
}
const seasonCleanupsPt = {
  header: { onClick: () => { seasonCleanupsCollapsed.value = !seasonCleanupsCollapsed.value }, class: 'cursor-pointer select-none' },
  togglebutton: _toggleButtonPt,
}
const moviesPt = {
  header: { onClick: () => { moviesCollapsed.value = !moviesCollapsed.value }, class: 'cursor-pointer select-none' },
  togglebutton: _toggleButtonPt,
}

/** Auto-trigger prepare when entering this step (no manual button needed) */
onMounted(async () => {
  if (!store.runPlan && canPrepare.value) {
    await store.prepareRunPlan(store.lastFilterCategories, store.lastFilterGreedy)
  }
})
</script>

<template>
  <div class="space-y-6 w-full max-w-full">
    <div class="card p-3 sm:p-5 space-y-5">
      <!-- Back button -->
      <div class="flex items-center gap-3">
        <Button
          label="Back"
          icon="pi pi-arrow-left"
          severity="secondary"
          @click="store.setWizardStep(2)"
        />
      </div>

      <!-- Active filter settings from step 2 -->
      <div class="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-surface-400">
        <span class="font-medium text-surface-500 uppercase tracking-wide">Filters:</span>
        <span
          v-for="cat in store.lastFilterCategories"
          :key="cat"
          class="flex items-center gap-1.5"
        >
          <span class="inline-block w-2 h-2 rounded-full" :class="categoryDots[cat]" />
          {{ categoryLabels[cat] || cat }}
        </span>
        <span class="text-surface-300 dark:text-surface-600">|</span>
        <span>{{ mediaTypeLabels[store.mediaType] || store.mediaType }}</span>
        <span v-if="store.lastFilterGreedy">
          <span class="text-surface-300 dark:text-surface-600">|</span>
          <span class="ml-5">Greedy</span>
        </span>
      </div>

      <p class="text-xs text-surface-400">
        Preview exactly which Radarr movies and Sonarr series will be affected before running cleanup.
      </p>
    </div>

    <!-- Search and summary bar -->
    <div
      v-if="store.runPlan"
      class="card px-3 sm:px-5 py-3 space-y-3"
    >
      <!-- Search input -->
      <IconField>
        <InputIcon class="pi pi-search" />
        <InputText
          v-model="searchQuery"
          placeholder="Search by title..."
          class="w-full"
        />
      </IconField>

      <!-- Summary tags (reflects selection, not full plan) -->
      <div class="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
        <Tag
          v-if="selectionSummary.fullSeriesCount > 0"
          severity="danger"
          :value="`${selectionSummary.fullSeriesCount} full series`"
        />
        <Tag
          v-if="selectionSummary.seasonCleanupCount > 0"
          severity="warn"
          :value="`${selectionSummary.seasonCleanupCount} season cleanup${selectionSummary.seasonCleanupCount !== 1 ? 's' : ''}`"
        />
        <Tag
          v-if="selectionSummary.movieCount > 0"
          severity="danger"
          :value="`${selectionSummary.movieCount} movie${selectionSummary.movieCount !== 1 ? 's' : ''}`"
        />
        <span class="text-surface-300">&middot;</span>
        <span class="font-medium text-surface-700 dark:text-surface-200">
          {{ selectionSummary.totalSizeFmt }}
        </span>
        <span class="text-surface-500">selected</span>
      </div>
    </div>

    <!-- Run plan details: Series first, then seasons, then movies -->
    <template v-if="hasResults">
      <!-- Series to delete entirely (Sonarr) -->
      <Panel
        v-if="visibleFullSeries.length > 0"
        v-model:collapsed="fullSeriesCollapsed"
        toggleable
        :pt="fullSeriesPt"
        class="max-w-full overflow-x-auto"
      >
        <template #header>
          <div class="flex items-center gap-2">
            <span class="font-semibold">Series to delete entirely</span>
            <Tag severity="danger" :value="String(visibleFullSeries.length)" rounded />
          </div>
        </template>
        <p class="text-xs text-surface-400 mb-3">Delete series and all files from Sonarr</p>
        <div class="overflow-x-auto">
          <DataTable
            v-model:selection="selectedFullSeries"
            :value="visibleFullSeries"
            stripedRows
            size="small"
            dataKey="sonarrSeriesId"
            sortField="sizeBytes"
            :sortOrder="-1"
          >
            <Column selectionMode="multiple" headerStyle="width: 3rem" />
            <Column field="title" header="Title" sortable />
            <Column field="libraryPath" header="Library Path" sortable />
            <Column field="seasonCount" header="Seasons" sortable />
            <Column header="Size" sortable sortField="sizeBytes">
              <template #body="{ data }">
                {{ formatSize(data.sizeBytes) }}
              </template>
            </Column>
          </DataTable>
        </div>
      </Panel>

      <!-- Seasons to clean (Sonarr) -->
      <Panel
        v-if="visibleSeasonCleanups.length > 0"
        v-model:collapsed="seasonCleanupsCollapsed"
        toggleable
        :pt="seasonCleanupsPt"
        class="max-w-full overflow-x-auto"
      >
        <template #header>
          <div class="flex items-center gap-2">
            <span class="font-semibold">Seasons to clean</span>
            <Tag severity="warn" :value="String(visibleSeasonCleanups.length)" rounded />
          </div>
        </template>
        <p class="text-xs text-surface-400 mb-3">Delete episode files and unmonitor seasons in Sonarr</p>
        <div class="overflow-x-auto">
          <DataTable
            v-model:selection="selectedSeasonCleanups"
            :value="visibleSeasonCleanups"
            stripedRows
            size="small"
            dataKey="sonarrSeriesId"
            sortField="totalSizeBytes"
            :sortOrder="-1"
          >
            <Column selectionMode="multiple" headerStyle="width: 3rem" />
            <Column field="title" header="Title" sortable />
            <Column header="Seasons">
              <template #body="{ data }">
                <div class="flex flex-wrap gap-1">
                  <Tag
                    v-for="sn in data.seasonNumbers"
                    :key="sn"
                    severity="secondary"
                    :value="`S${String(sn).padStart(2, '0')}`"
                    rounded
                  />
                </div>
              </template>
            </Column>
            <Column header="Total Seasons" sortable sortField="totalSeasonCount">
              <template #body="{ data }">
                {{ data.seasonNumbers.length }} of {{ data.totalSeasonCount }}
              </template>
            </Column>
            <Column header="Episodes" sortable sortField="episodeFileCount">
              <template #body="{ data }">
                {{ data.episodeFileCount }} of {{ data.totalEpisodeCount }}
              </template>
            </Column>
            <Column header="Size" sortable sortField="totalSizeBytes">
              <template #body="{ data }">
                {{ formatSize(data.totalSizeBytes) }}
              </template>
            </Column>
          </DataTable>
        </div>
      </Panel>

      <!-- Movies to delete (Radarr) -->
      <Panel
        v-if="visibleMovies.length > 0"
        v-model:collapsed="moviesCollapsed"
        toggleable
        :pt="moviesPt"
        class="max-w-full overflow-x-auto"
      >
        <template #header>
          <div class="flex items-center gap-2">
            <span class="font-semibold">Movies to delete</span>
            <Tag severity="danger" :value="String(visibleMovies.length)" rounded />
          </div>
        </template>
        <p class="text-xs text-surface-400 mb-3">Delete movie and files from Radarr</p>
        <div class="overflow-x-auto">
          <DataTable
            v-model:selection="selectedMovies"
            :value="visibleMovies"
            stripedRows
            size="small"
            dataKey="radarrId"
            sortField="sizeBytes"
            :sortOrder="-1"
          >
            <Column selectionMode="multiple" headerStyle="width: 3rem" />
            <Column field="title" header="Title" sortable />
            <Column field="libraryPath" header="Library Path" sortable />
            <Column header="Size" sortable sortField="sizeBytes">
              <template #body="{ data }">
                {{ formatSize(data.sizeBytes) }}
              </template>
            </Column>
          </DataTable>
        </div>
      </Panel>
    </template>

    <!-- Empty state -->
    <div
      v-else-if="isEmpty"
      class="card p-6 sm:p-12 flex flex-col items-center justify-center text-center"
    >
      <p class="text-surface-400 text-lg">Nothing to clean up</p>
      <p class="text-xs text-surface-400 mt-2">
        The selected filters did not produce any items with valid library IDs.
      </p>
    </div>
  </div>
</template>
