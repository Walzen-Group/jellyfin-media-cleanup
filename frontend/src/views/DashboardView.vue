<script setup lang="ts">
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
    <AnalysisControls />

    <!-- Results -->
    <template v-if="store.currentJob?.result">
      <SummaryPanel :summary="store.currentJob.result.summary" />

      <Tabs value="series">
        <TabList>
          <Tab value="series">Series ({{ store.allSeries.length }})</Tab>
          <Tab value="movies">Movies ({{ store.allMovies.length }})</Tab>
        </TabList>
        <TabPanels>
          <TabPanel value="series">
            <div class="pt-4">
              <SeriesTable :series="store.allSeries" :month-threshold="store.monthThreshold" />
            </div>
          </TabPanel>
          <TabPanel value="movies">
            <div class="pt-4">
              <MovieTable :movies="store.allMovies" />
            </div>
          </TabPanel>
        </TabPanels>
      </Tabs>
    </template>

    <!-- Loading or empty state -->
    <div
      v-else-if="!store.isAnalyzing"
      class="card p-12 flex flex-col items-center justify-center text-center text-surface-500"
    >
      <template v-if="store.loading">
        <ProgressSpinner style="width: 36px; height: 36px" strokeWidth="4" />
      </template>
      <template v-else>
        <p class="text-xl mb-2">No analysis results yet</p>
        <p class="text-sm">Configure options above and click "Run Analysis" to start.</p>
      </template>
    </div>
  </div>
</template>
