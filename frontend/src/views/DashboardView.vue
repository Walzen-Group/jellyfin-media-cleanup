<script setup lang="ts">
/**
 * Main dashboard view wrapped in a PrimeVue Stepper.
 * Step 1 "Analysis" - run analysis, view full results
 * Step 2 "Selection" - filter by category and greedy mode
 * Step 3 "Prepare" - dry-run deletion preview (run plan)
 * Step 4 "Cleanup" - execute or simulate deletion
 */

import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useJobStore } from '../stores/jobStore'
import Stepper from 'primevue/stepper'
import StepList from 'primevue/steplist'
import StepItem from 'primevue/step'
import StepPanels from 'primevue/steppanels'
import StepPanel from 'primevue/steppanel'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanels from 'primevue/tabpanels'
import TabPanel from 'primevue/tabpanel'
import Button from 'primevue/button'
import ProgressSpinner from 'primevue/progressspinner'
import Message from 'primevue/message'
import AnalysisControls from '../components/AnalysisControls.vue'
import SummaryPanel from '../components/SummaryPanel.vue'
import MovieTable from '../components/MovieTable.vue'
import SeriesTable from '../components/SeriesTable.vue'
import SelectionPanel from '../components/SelectionPanel.vue'
import PreparePanel from '../components/PreparePanel.vue'
import CleanupPanel from '../components/CleanupPanel.vue'

const store = useJobStore()
const { isCleanupRunning, currentJob } = storeToRefs(store)

const autoKeepCount = computed(() => {
  const ak = currentJob.value?.result?.autoKeep
  if (!ak) return 0
  return (ak.movies?.length ?? 0) + (ak.series?.length ?? 0)
})
</script>

<template>
  <Stepper v-model:value="store.wizardStep" linear>
    <StepList>
      <StepItem :value="1" :disabled="isCleanupRunning">Analysis</StepItem>
      <StepItem :value="2" :disabled="isCleanupRunning">Selection</StepItem>
      <StepItem :value="3" :disabled="isCleanupRunning">Prepare</StepItem>
      <StepItem :value="4">Cleanup</StepItem>
    </StepList>
    <StepPanels>
      <StepPanel :value="1">
        <div class="space-y-6">
          <!-- Form to start/cancel analysis and set thresholds -->
          <AnalysisControls>
            <template #actions>
              <Button
                v-if="store.currentJob?.result"
                label="Next"
                icon="pi pi-arrow-right"
                iconPos="right"
                @click="store.setWizardStep(2)"
              />
            </template>
          </AnalysisControls>

          <!-- Auto-keep notification: items re-requested after prior deletion -->
          <Message
            v-if="autoKeepCount > 0"
            severity="info"
            :closable="false"
          >
            {{ autoKeepCount }} item(s) were re-requested after deletion and have been automatically tagged as Keep.
          </Message>

          <!-- Show results when a completed job result is available -->
          <template v-if="store.currentJob?.result">
            <!-- Summary statistics: counts and sizes across all categories -->
            <SummaryPanel :summary="store.currentJob.result.summary" />

            <!-- Flattened tables with filtering/sorting. Series shown by default (first tab). -->
            <div class="card px-1 py-2 sm:p-5">
              <Tabs value="series">
                <TabList>
                  <Tab value="series">Series ({{ store.allSeries.length }})</Tab>
                  <Tab value="movies">Movies ({{ store.allMovies.length }})</Tab>
                </TabList>
                <TabPanels>
                  <TabPanel value="series">
                    <div class="pt-4">
                      <SeriesTable :series="store.allSeries" />
                    </div>
                  </TabPanel>
                  <TabPanel value="movies">
                    <div class="pt-4">
                      <MovieTable :movies="store.allMovies" />
                    </div>
                  </TabPanel>
                </TabPanels>
              </Tabs>
            </div>

          </template>

          <!-- Spinner shown while fetching initial job from API -->
          <div
            v-else-if="store.loading"
            class="py-16 flex items-center justify-center"
          >
            <ProgressSpinner style="width: 96px; height: 96px" strokeWidth="6" />
          </div>

          <!-- Empty state: no job result yet; prompt user to run analysis -->
          <div
            v-else-if="!store.isAnalyzing"
            class="card p-6 sm:p-12 flex flex-col items-center justify-center text-center text-surface-500"
          >
            <p class="text-xl mb-2">No analysis results yet</p>
            <p class="text-sm">Configure options above and click "Run Analysis" to start.</p>
          </div>
        </div>
      </StepPanel>

      <StepPanel :value="2">
        <SelectionPanel />
      </StepPanel>

      <StepPanel :value="3">
        <PreparePanel />
      </StepPanel>

      <StepPanel :value="4">
        <CleanupPanel />
      </StepPanel>
    </StepPanels>
  </Stepper>
</template>
