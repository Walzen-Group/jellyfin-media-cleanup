<script setup lang="ts">
import { ref, computed } from 'vue'
import DataTable, { type DataTableFilterMeta } from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import MultiSelect from 'primevue/multiselect'
import type { MovieRow, MediaStatus } from '../types/api'
import { formatSize } from '../utils/format'

const props = defineProps<{
  movies: MovieRow[]
}>()

const statusOptions = [
  { label: 'Recently Watched', value: 'recent' },
  { label: 'Not Recently Watched', value: 'old' },
  { label: 'Kept', value: 'kept' },
  { label: 'Unmatched', value: 'unmatched' },
  { label: 'Never Watched', value: 'never' },
  { label: 'New (unwatched)', value: 'never_new' },
  { label: 'Collision', value: 'collision' },
]

const statusLabels: Record<MediaStatus, string> = {
  recent: 'Recent',
  old: 'Not Recent',
  mixed: 'Mixed',
  kept: 'Kept',
  unmatched: 'Unmatched',
  never: 'Never',
  never_new: 'New',
  collision: 'Collision'
}

const statusColors: Record<MediaStatus, string> = {
  recent: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  old: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
  mixed: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
  kept: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
  unmatched: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
  never: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300',
  never_new: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/40 dark:text-cyan-300',
  collision: 'bg-fuchsia-100 text-fuchsia-800 dark:bg-fuchsia-900/40 dark:text-fuchsia-300',
}

const filters = ref<DataTableFilterMeta>({
  global: { value: null, matchMode: 'contains' },
  status: { value: [], matchMode: 'in' },
})

const filteredCount = computed(() => {
  // Approximate — PrimeVue handles actual filtering internally
  let result = props.movies
  const statusVal = (filters.value.status as { value: string[] }).value
  if (statusVal.length) {
    result = result.filter(m => statusVal.includes(m.status))
  }
  const globalVal = (filters.value.global as { value: string | null }).value
  if (globalVal) {
    const q = globalVal.toLowerCase()
    result = result.filter(m => m.title.toLowerCase().includes(q) || (m.libraryPath?.toLowerCase().includes(q) ?? false))
  }
  return result.length
})
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center gap-3">
      <InputText
        v-model="(filters.global as any).value"
        placeholder="Search movies..."
        class="!text-sm"
      />
      <span class="text-sm text-surface-500 ml-auto">
        {{ filteredCount }} of {{ movies.length }} movies
      </span>
    </div>

    <DataTable
      :value="movies"
      v-model:filters="filters"
      filterDisplay="row"
      :globalFilterFields="['title', 'libraryPath']"
      sortField="sizeBytes"
      :sortOrder="-1"
      paginator
      :rows="50"
      :rowsPerPageOptions="[25, 50, 100]"
      size="small"
      tableClass="text-sm"
    >
      <Column field="title" header="Title" sortable style="width: 40%">
        <template #body="{ data }">
          <span class="font-medium">{{ data.title }}</span>
        </template>
      </Column>
      <Column field="status" header="Status" :showFilterMenu="false" :showClearButton="false" style="width: 180px">
        <template #body="{ data }">
          <span class="inline-block rounded-full px-2.5 py-0.5 text-xs font-medium" :class="statusColors[data.status as MediaStatus]">
            {{ statusLabels[data.status as MediaStatus] }}
          </span>
        </template>
        <template #filter="{ filterModel, filterCallback }">
          <MultiSelect
            v-model="filterModel.value"
            :options="statusOptions"
            optionLabel="label"
            optionValue="value"
            placeholder="All"
            :showToggleAll="false"
            display="comma"
            @change="filterCallback()"
          >
            <template #option="{ option }">
              <span class="inline-block rounded-full px-2.5 py-0.5 text-xs font-medium" :class="statusColors[option.value as MediaStatus]">
                {{ option.label }}
              </span>
            </template>
          </MultiSelect>
        </template>
      </Column>
      <Column field="matchMethod" header="Match" sortable style="width: 110px">
        <template #body="{ data }">
          <span class="text-xs text-surface-500">{{ data.matchMethod ?? 'unmatched' }}</span>
        </template>
      </Column>
      <Column field="sizeBytes" header="Size" sortable style="width: 100px">
        <template #body="{ data }">
          <span class="tabular-nums">{{ formatSize(data.sizeBytes) }}</span>
        </template>
      </Column>
      <Column field="libraryPath" header="Library Path" sortable style="min-width: 200px">
        <template #body="{ data }">
          <span v-if="data.libraryPath" class="text-xs text-surface-500 font-mono break-all" :title="data.libraryPath">
            {{ data.libraryPath }}
          </span>
        </template>
      </Column>
    </DataTable>
  </div>
</template>
