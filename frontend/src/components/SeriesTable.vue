<script setup lang="ts">
import { ref, computed } from 'vue'
import DataTable, { type DataTableFilterMeta } from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import MultiSelect from 'primevue/multiselect'
import SeasonDot from './SeasonDot.vue'
import type { SeriesRow, MediaStatus } from '../types/api'
import { formatSize, formatDate } from '../utils/format'

const props = defineProps<{
  series: SeriesRow[]
}>()

const expandedRows = ref<Record<string, boolean>>({})

const statusOptions = [
  { label: 'Recently Watched', value: 'recent' },
  { label: 'Not Recently Watched', value: 'old' },
  { label: 'Mixed', value: 'mixed' },
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
  collision: 'Collision',
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
  let result = props.series
  const statusVal = (filters.value.status as { value: string[] }).value
  if (statusVal.length) {
    result = result.filter(s => statusVal.includes(s.status))
  }
  const globalVal = (filters.value.global as { value: string | null }).value
  if (globalVal) {
    const q = globalVal.toLowerCase()
    result = result.filter(s => s.title.toLowerCase().includes(q) || (s.libraryPath?.toLowerCase().includes(q) ?? false))
  }
  return result.length
})
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center gap-3">
      <InputText
        v-model="(filters.global as any).value"
        placeholder="Search series..."
        class="!text-sm"
      />
      <span class="text-sm text-surface-500 ml-auto">
        {{ filteredCount }} of {{ series.length }} series
      </span>
    </div>

    <DataTable
      v-model:expandedRows="expandedRows"
      v-model:filters="filters"
      filterDisplay="row"
      :globalFilterFields="['title', 'libraryPath']"
      :value="series"
      dataKey="title"
      sortField="sizeBytes"
      :sortOrder="-1"
      paginator
      :rows="50"
      :rowsPerPageOptions="[25, 50, 100]"
      size="small"
      tableClass="text-sm"
    >
      <Column expander style="width: 40px" />
      <Column field="title" header="Title" sortable style="width: 40%">
        <template #body="{ data }">
          <span
            class="font-medium cursor-pointer hover:underline"
            @click="expandedRows[data.title] ? delete expandedRows[data.title] : (expandedRows[data.title] = true)"
          >{{ data.title }}</span>
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
      <Column header="Seasons" style="width: 140px">
        <template #body="{ data }">
          <div class="flex gap-px items-center" style="width: 170px">
            <SeasonDot
              v-for="s in data.seasons"
              :key="s.seasonNumber"
              :season-number="s.seasonNumber"
              :last-played="s.lastPlayed || null"
              :status="s.status"
            />
          </div>
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

      <template #expansion="{ data }">
        <div class="pl-10 pr-4 py-2">
          <DataTable :value="data.seasons" size="small" tableClass="text-xs" tableStyle="table-layout: fixed">
            <Column field="seasonNumber" header="Season" sortable>
              <template #body="{ data: s }">
                S{{ String(s.seasonNumber).padStart(2, '0') }}
              </template>
            </Column>
            <Column header="Recent">
              <template #body="{ data: s }">
                <span
                  class="inline-block w-2.5 h-2.5 rounded-full"
                  :class="s.status === 'recent' ? 'bg-emerald-400/70 dark:bg-emerald-400/60' : s.status === 'old' ? 'bg-rose-400/70 dark:bg-rose-400/60' : s.status === 'kept' ? 'bg-amber-400/70 dark:bg-amber-400/60' : s.status === 'collision' ? 'bg-fuchsia-400/70 dark:bg-fuchsia-400/60' : 'bg-surface-300 dark:bg-surface-600'"
                />
              </template>
            </Column>
            <Column header="Available">
              <template #body="{ data: s }">
                <span class="text-xs" :class="s.sizeBytes > 0 ? 'text-emerald-500' : 'text-surface-400'">
                  {{ s.sizeBytes > 0 ? 'Yes' : 'No' }}
                </span>
              </template>
            </Column>
            <Column field="lastPlayed" :header="data.status === 'never' || data.status === 'never_new' ? 'Added' : 'Last Played'" sortable>
              <template #body="{ data: s }">
                {{ s.lastPlayed ? formatDate(s.lastPlayed) : (data.added ? formatDate(data.added) : '–') }}
              </template>
            </Column>
            <Column header="Episodes" sortable>
              <template #body="{ data: s }">
                <span class="tabular-nums">{{ s.totalEpisodes || '–' }}</span>
              </template>
            </Column>
            <Column field="sizeBytes" header="Size" sortable>
              <template #body="{ data: s }">
                <span class="tabular-nums">{{ formatSize(s.sizeBytes) }}</span>
              </template>
            </Column>
          </DataTable>
          <div v-if="data.libraryPath" class="mt-2 text-xs text-surface-500 font-mono">
            {{ data.libraryPath }}
          </div>
        </div>
      </template>
    </DataTable>
  </div>
</template>
