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
import Slider from 'primevue/slider'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanels from 'primevue/tabpanels'
import TabPanel from 'primevue/tabpanel'
import MovieTable from './MovieTable.vue'
import SeriesTable from './SeriesTable.vue'
import FilteredSummaryBar from './FilteredSummaryBar.vue'
import { formatSize } from '../utils/format'

const store = useJobStore()
const { mediaType } = storeToRefs(store)

const MAX_SIZE_SLIDER = 200  // represents 200 GB; treated as "no limit"

// Initialize from restored filter state (backend wizard sync) or empty defaults
const categories = ref<string[]>([...store.lastFilterCategories])
const greedy = ref(store.lastFilterGreedy)
const sizeRange = ref<[number, number]>([
  store.lastFilterMinSizeBytes > 0 ? Math.round(store.lastFilterMinSizeBytes / (1024 * 1024 * 1024)) : 0,
  store.lastFilterMaxSizeBytes != null ? Math.round(store.lastFilterMaxSizeBytes / (1024 * 1024 * 1024)) : MAX_SIZE_SLIDER,
])
const appliedCategories = ref<string[]>([...store.lastFilterCategories])
const appliedGreedy = ref(store.lastFilterGreedy)
const appliedMediaType = ref<string>(store.mediaType)
const appliedSizeRange = ref<[number, number]>([...sizeRange.value] as [number, number])

/** Convert a slider GB value to bytes for display (e.g. formatSize(sliderGbToBytes(5)) => "5.0 GB") */
function sliderGbToBytes(gb: number): number {
  return gb * 1024 * 1024 * 1024
}

/** Human-readable label for a slider position. Returns "no limit" when at MAX_SIZE_SLIDER. */
function formatSliderValue(gb: number): string {
  if (gb >= MAX_SIZE_SLIDER) return 'no limit'
  return formatSize(sliderGbToBytes(gb))
}

/** True when the current settings differ from what was last filtered */
const filterStale = computed(() => {
  if (!store.filteredResult) return true
  const catsChanged = JSON.stringify([...categories.value].sort()) !== JSON.stringify([...appliedCategories.value].sort())
  const sizeChanged = sizeRange.value[0] !== appliedSizeRange.value[0] || sizeRange.value[1] !== appliedSizeRange.value[1]
  return catsChanged || greedy.value !== appliedGreedy.value || mediaType.value !== appliedMediaType.value || sizeChanged
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
  // "unmatched" items have no library entry; user can opt in to include them for pruning
  // zinc-400/500 gives a neutral grey that sits visibly above surface card backgrounds in both light and dark mode
  { label: 'Unmatched', value: 'unmatched', dot: 'bg-zinc-400/70 dark:bg-zinc-500/70' },
]

async function filter() {
  const minSizeBytes = sizeRange.value[0] > 0 ? sliderGbToBytes(sizeRange.value[0]) : 0
  const maxSizeBytes = sizeRange.value[1] >= MAX_SIZE_SLIDER ? null : sliderGbToBytes(sizeRange.value[1])
  await store.applyFilter(categories.value, greedy.value, minSizeBytes, maxSizeBytes)
  appliedCategories.value = [...categories.value]
  appliedGreedy.value = greedy.value
  appliedMediaType.value = mediaType.value
  appliedSizeRange.value = [...sizeRange.value] as [number, number]
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
      <!-- Category selection, media type, size range, and greedy mode -->
      <div class="space-y-5">
        <!-- Row 1: categories + media type + size range side by side on sm+, stacked on mobile -->
        <div class="flex flex-col sm:flex-row gap-6 sm:gap-10">
          <!-- Categories to prune -->
          <div class="flex-1">
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

          <!-- Media type -->
          <div class="flex-1">
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

          <!-- File size range -->
          <div class="flex-1">
            <label class="block text-xs font-medium text-surface-500 mb-3 uppercase tracking-wide">
              File size range
            </label>
            <div class="px-1">
              <Slider v-model="sizeRange" :min="0" :max="MAX_SIZE_SLIDER" :step="1" range class="w-full" />
            </div>
            <p class="text-sm text-surface-400 mt-2">
              <span class="text-surface-600 dark:text-surface-300 font-medium">{{ formatSliderValue(sizeRange[0]) }}</span>
              <span class="mx-1.5">-</span>
              <span class="text-surface-600 dark:text-surface-300 font-medium">{{ formatSliderValue(sizeRange[1]) }}</span>
            </p>
          </div>
        </div>

        <!-- Row 2: greedy mode always below the three controls above -->
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

      <!-- Action buttons -->
      <div class="flex items-center gap-3">
        <Button
          label="Back"
          icon="pi pi-arrow-left"
          severity="secondary"
          @click="store.setWizardStep(1)"
        />
        <Button
          :label="store.filterLoading ? 'Filtering...' : (filterStale && store.filteredResult ? 'Re-filter' : 'Filter')"
          :icon="store.filterLoading ? 'pi pi-spin pi-spinner' : 'pi pi-filter'"
          :disabled="categories.length === 0 || store.filterLoading"
          :severity="filterStale && store.filteredResult ? 'warn' : undefined"
          @click="filter"
        />
      </div>
    </div>

    <!-- Next step button -->
    <div v-if="store.filteredResult" class="card p-3 sm:p-5">
      <div class="flex items-center gap-3">
        <Button
          :label="nextLoading ? 'Preparing...' : 'Next'"
          :icon="nextLoading ? 'pi pi-spin pi-spinner' : 'pi pi-arrow-right'"
          :iconPos="nextLoading ? 'left' : 'right'"
          :disabled="filterStale || nextLoading"
          @click="proceedToPrepare"
        />
        <span v-if="filterStale" class="text-xs text-yellow-500">Settings changed. Re-run filter first.</span>
        <span v-else class="text-xs text-surface-400">Proceed to prepare a deletion plan</span>
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
