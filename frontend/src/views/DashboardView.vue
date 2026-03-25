<script setup lang="ts">
/**
 * Main dashboard view. Layout:
 * 1. AnalysisControls: form to start/cancel analysis, set thresholds
 * 2. SummaryPanel: statistics grid (shows when result exists)
 * 3. Tabbed tables: flattened movie/series data from the result (shows when result exists)
 * 4. Loading/empty state: spinner while fetching initial job, or "no results yet" message
 *
 * Data flows from store (populated via API + WebSocket) down to each component as props.
 */

import { useJobStore } from '../stores/jobStore'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanels from 'primevue/tabpanels'
import TabPanel from 'primevue/tabpanel'
import ProgressSpinner from 'primevue/progressspinner'
import AnalysisControls from '../components/AnalysisControls.vue'
import SummaryPanel from '../components/SummaryPanel.vue'
import MovieTable from '../components/MovieTable.vue'
import SeriesTable from '../components/SeriesTable.vue'

const store = useJobStore()
</script>

<template>
  <div class="space-y-6">
    <!-- Form to start/cancel analysis and set thresholds -->
    <AnalysisControls />

    <!-- Show results when a completed job result is available -->
    <template v-if="store.currentJob?.result">
      <!-- Summary statistics: counts and sizes across all categories -->
      <SummaryPanel :summary="store.currentJob.result.summary" />

      <!-- Flattened tables with filtering/sorting. Series shown by default (first tab). -->
      <Tabs value="series">
        <TabList>
          <Tab value="series">Series ({{ store.allSeries.length }})</Tab>
          <Tab value="movies">Movies ({{ store.allMovies.length }})</Tab>
        </TabList>
        <TabPanels>
          <TabPanel value="series">
            <div class="pt-4">
              <!-- Unified series table with status column, expandable rows, collision info -->
              <SeriesTable :series="store.allSeries" />
            </div>
          </TabPanel>
          <TabPanel value="movies">
            <div class="pt-4">
              <!-- Unified movies table with status column, match method, library path -->
              <MovieTable :movies="store.allMovies" />
            </div>
          </TabPanel>
        </TabPanels>
      </Tabs>
    </template>

    <!-- Show loading spinner while restoring initial job, or empty state if no result -->
    <div
      v-else-if="!store.isAnalyzing"
      class="card p-12 flex flex-col items-center justify-center text-center text-surface-500"
    >
      <template v-if="store.loading">
        <!-- Spinner shown while fetching initial job from API -->
        <ProgressSpinner style="width: 36px; height: 36px" strokeWidth="4" />
      </template>
      <template v-else>
        <!-- Empty state: no job result yet; prompt user to run analysis -->
        <p class="text-xl mb-2">No analysis results yet</p>
        <p class="text-sm">Configure options above and click "Run Analysis" to start.</p>
      </template>
    </div>
  </div>
</template>
