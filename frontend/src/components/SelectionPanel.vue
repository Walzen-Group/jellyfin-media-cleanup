<script setup lang="ts">
/**
 * Step 2 of the wizard: select categories to prune and greedy mode.
 * Calls store.applyFilter() which hits the backend filter endpoint.
 * When results are available, displays them using the same table components as Step 1.
 */

import { ref, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useJobStore } from '../stores/jobStore'
import Checkbox from 'primevue/checkbox'
import ToggleSwitch from 'primevue/toggleswitch'
import RadioButton from 'primevue/radiobutton'
import Button from 'primevue/button'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanels from 'primevue/tabpanels'
import TabPanel from 'primevue/tabpanel'
import MovieTable from './MovieTable.vue'
import SeriesTable from './SeriesTable.vue'
import FilteredSummaryBar from './FilteredSummaryBar.vue'

const store = useJobStore()
const { mediaType } = storeToRefs(store)

const categories = ref<string[]>([])
const greedy = ref(false)
const appliedCategories = ref<string[]>([])
const appliedGreedy = ref(false)
const appliedMediaType = ref<string>('all')

/** True when the current settings differ from what was last filtered */
const filterStale = computed(() => {
  if (!store.filteredResult) return true
  const catsChanged = JSON.stringify([...categories.value].sort()) !== JSON.stringify([...appliedCategories.value].sort())
  return catsChanged || greedy.value !== appliedGreedy.value || mediaType.value !== appliedMediaType.value
})

const mediaTypeOptions = [
  { label: 'All', value: 'all' as const },
  { label: 'Movies Only', value: 'movies' as const },
  { label: 'Series Only', value: 'series' as const },
]

const categoryOptions = [
  { label: 'Not recently watched', value: 'old', dot: 'bg-rose-400/70 dark:bg-rose-400/60' },
  { label: 'Never watched', value: 'never', dot: 'bg-purple-400/70 dark:bg-purple-400/60' },
  { label: 'New (unwatched)', value: 'never_new', dot: 'bg-cyan-400/70 dark:bg-cyan-400/60' },
]

async function filter() {
  await store.applyFilter(categories.value, greedy.value)
  appliedCategories.value = [...categories.value]
  appliedGreedy.value = greedy.value
  appliedMediaType.value = mediaType.value
}

const nextLoading = ref(false)
async function proceedToPrepare() {
  nextLoading.value = true
  try {
    await store.prepareRunPlan(store.lastFilterCategories, store.lastFilterGreedy)
    store.setWizardStep(3)
  } finally {
    nextLoading.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="card p-3 sm:p-5 space-y-5">
      <!-- Category selection, media type, and greedy mode -->
      <div class="flex flex-col sm:flex-row gap-6">
        <div class="space-y-5">
          <div>
            <label class="block text-xs font-medium text-surface-500 mb-3 uppercase tracking-wide">
              Categories to prune
            </label>
            <div class="flex flex-col gap-3">
              <div
                v-for="opt in categoryOptions"
                :key="opt.value"
                class="flex items-center gap-2"
              >
                <Checkbox
                  v-model="categories"
                  :inputId="opt.value"
                  :value="opt.value"
                />
                <span class="inline-block w-2.5 h-2.5 rounded-full" :class="opt.dot" />
                <label :for="opt.value" class="cursor-pointer">{{ opt.label }}</label>
              </div>
            </div>
          </div>

          <div>
            <div class="flex items-center gap-3">
              <ToggleSwitch v-model="greedy" inputId="greedy-toggle" />
              <label for="greedy-toggle" class="cursor-pointer font-medium">Greedy mode</label>
            </div>
            <p class="text-xs text-surface-400 mt-1.5" style="padding-left: 3.25rem;">
              Include series where only some seasons match (mixed status). When off, only series where all seasons match are included.
            </p>
          </div>
        </div>

        <div class="sm:ml-8">
          <label class="block text-xs font-medium text-surface-500 mb-3 uppercase tracking-wide">
            Media type
          </label>
          <div class="flex flex-col gap-3">
            <div
              v-for="opt in mediaTypeOptions"
              :key="opt.value"
              class="flex items-center gap-2"
            >
              <RadioButton
                v-model="mediaType"
                :inputId="'media-' + opt.value"
                :value="opt.value"
              />
              <label :for="'media-' + opt.value" class="cursor-pointer">{{ opt.label }}</label>
            </div>
          </div>
        </div>
      </div>

      <!-- Action buttons -->
      <div class="flex items-center gap-3">
        <Button
          label="Back"
          icon="pi pi-arrow-left"
          severity="secondary"
          @click="store.setWizardStep(1)"
        />
        <Button
          label="Filter"
          icon="pi pi-filter"
          :loading="store.filterLoading"
          :disabled="categories.length === 0 || store.filterLoading"
          @click="filter"
        />
      </div>
    </div>

    <!-- Next step button -->
    <div v-if="store.filteredResult" class="card p-3 sm:p-5">
      <div class="flex items-center gap-3">
        <Button
          label="Next"
          icon="pi pi-arrow-right"
          iconPos="right"
          :loading="nextLoading"
          :disabled="filterStale || nextLoading"
          @click="proceedToPrepare"
        />
        <span v-if="filterStale" class="text-xs text-yellow-500">Settings changed. Re-run filter first.</span>
        <span v-else class="text-xs text-surface-400">Proceed to prepare a dry-run deletion plan</span>
      </div>
    </div>

    <!-- Filtered results -->
    <template v-if="store.filteredResult">
      <FilteredSummaryBar :summary="store.filteredResult.summary" />

      <div class="card px-1 py-2 sm:p-5">
        <Tabs value="series">
          <TabList>
            <Tab value="series">Series ({{ store.filteredSeries.length }})</Tab>
            <Tab value="movies">Movies ({{ store.filteredMovies.length }})</Tab>
          </TabList>
          <TabPanels>
            <TabPanel value="series">
              <div class="pt-4">
                <SeriesTable :series="store.filteredSeries" :active-categories="appliedCategories" />
              </div>
            </TabPanel>
            <TabPanel value="movies">
              <div class="pt-4">
                <MovieTable :movies="store.filteredMovies" />
              </div>
            </TabPanel>
          </TabPanels>
        </Tabs>
      </div>
    </template>
  </div>
</template>
