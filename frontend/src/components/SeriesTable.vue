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
  activeCategories?: string[]
}>()

const expandedRows = ref<Record<string, boolean>>({})

/**
 * Returns true when a season should be visually dimmed (status not in active categories).
 * Only applies when activeCategories is provided.
 */
function isSeasonInactive(seasonStatus: string): boolean {
  if (!props.activeCategories?.length) return false
  return !props.activeCategories.includes(seasonStatus)
}

/**
 * Returns opacity class for expanded season table rows based on whether their status
 * is in the active categories. Only applies when activeCategories is provided.
 */
function seasonRowClass(seasonStatus: string): string {
  if (!props.activeCategories?.length) return ''
  return props.activeCategories.includes(seasonStatus) ? '' : 'opacity-20'
}

const statusOptions = [
  { label: 'Recently Watched', value: 'recent' },
  { label: 'Not Recently Watched', value: 'old' },
  { label: 'Some Recently Watched', value: 'mixed' },
  { label: 'Kept', value: 'kept' },
  { label: 'Auto-Kept', value: 'auto_keep' },
  { label: 'Unmatched', value: 'unmatched' },
  { label: 'Never Watched', value: 'never' },
  { label: 'New (unwatched)', value: 'never_new' },
  { label: 'Collision', value: 'collision' },
]

const statusLabels: Record<MediaStatus, string> = {
  recent: 'Recently',
  old: 'Not Recent',
  mixed: 'Some',
  kept: 'Kept',
  auto_keep: 'Auto-Kept',
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
  auto_keep: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  unmatched: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
  never: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300',
  never_new: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/40 dark:text-cyan-300',
  collision: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300',
}

/**
 * Filter state for the DataTable. Global filter uses 'contains', status uses 'in' (multi-select).
 * Note: PrimeVue doesn't expose filtered row count as a reactive value, so we compute
 * filteredCount manually by replicating the filter logic.
 */
const filters = ref<DataTableFilterMeta>({
  global: { value: null, matchMode: 'contains' },
  status: { value: [], matchMode: 'in' },
})

/**
 * Manually compute the filtered row count to display "N of M" summary.
 * Applies both status filter (if selected) and global search filter.
 */
const filteredCount = computed(() => {
  let result = props.series
  // Apply status multi-select filter
  const statusVal = (filters.value.status as { value: string[] }).value
  if (statusVal.length) {
    result = result.filter(s => statusVal.includes(s.status))
  }
  // Apply global search filter (title and libraryPath)
  const globalVal = (filters.value.global as { value: string | null }).value
  if (globalVal) {
    const q = globalVal.toLowerCase()
    result = result.filter(s => s.title.toLowerCase().includes(q) || (s.libraryPath?.toLowerCase().includes(q) ?? false))
  }
  return result.length
})
</script>

<template>
  <div class="space-y-3 overflow-x-auto">
    <div class="flex flex-wrap items-center gap-3">
      <InputText
        v-model="(filters.global as any).value"
        placeholder="Search series..."
        class="!text-sm w-72"
      />
      <!-- Season dot color legend -->
      <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-surface-400">
        <span class="flex items-center gap-1"><span class="inline-block w-2 h-2 rounded-sm bg-emerald-400/70" />Recent</span>
        <span class="flex items-center gap-1"><span class="inline-block w-2 h-2 rounded-sm bg-rose-400/70" />Not recent</span>
        <span class="flex items-center gap-1"><span class="inline-block w-2 h-2 rounded-sm bg-purple-400/70" />Never</span>
        <span class="flex items-center gap-1"><span class="inline-block w-2 h-2 rounded-sm bg-cyan-400/70" />New</span>
        <span class="flex items-center gap-1"><span class="inline-block w-2 h-2 rounded-sm bg-amber-400/70" />Kept</span>
        <span class="flex items-center gap-1"><span class="inline-block w-2 h-2 rounded-sm bg-surface-300 dark:bg-surface-600" />Unmatched</span>
      </div>
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
      <Column field="status" header="Watch Status" :showFilterMenu="false" :showClearButton="false" style="width: 180px">
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
              :inactive="isSeasonInactive(s.status)"
            />
          </div>
        </template>
      </Column>
      <!-- Match method: "path", "fuzzy", or null when matching was not attempted (never-watched, kept) -->
      <Column field="matchMethod" header="Match" sortable style="width: 110px">
        <template #body="{ data }">
          <!-- Show a neutral dash when matchMethod is null; only actually-unmatched rows have status==="unmatched" -->
          <span class="text-xs text-surface-500">{{ data.matchMethod ?? '-' }}</span>
        </template>
      </Column>
      <Column field="sizeBytes" header="Size" sortable style="width: 100px">
        <template #body="{ data }">
          <span class="tabular-nums">{{ formatSize(data.sizeBytes) }}</span>
        </template>
      </Column>

      <!-- Expandable row: shows all seasons for this series, collision details (if any), and library path -->
      <template #expansion="{ data }">
        <div class="pl-2 pr-1 sm:pl-10 sm:pr-4 py-2">
          <!-- Season breakdown table: watch status, available/on-disk, last played, episode counts, sizes -->
          <DataTable :value="data.seasons" size="small" tableClass="text-xs" tableStyle="table-layout: fixed" :rowClass="(s: any) => seasonRowClass(s.status)">
            <Column field="seasonNumber" header="Season" sortable>
              <template #body="{ data: s }">
                S{{ String(s.seasonNumber).padStart(2, '0') }}
              </template>
            </Column>
            <!-- Color dot indicates season watch status -->
            <Column header="Recent">
              <template #body="{ data: s }">
                <span
                  class="inline-block w-2.5 h-2.5 rounded-full"
                  :class="s.status === 'recent' ? 'bg-emerald-400/70 dark:bg-emerald-400/60' : s.status === 'old' ? 'bg-rose-400/70 dark:bg-rose-400/60' : s.status === 'kept' ? 'bg-amber-400/70 dark:bg-amber-400/60' : s.status === 'auto_keep' ? 'bg-yellow-400/70 dark:bg-yellow-400/60' : s.status === 'collision' ? 'bg-orange-400/70 dark:bg-orange-400/60' : 'bg-surface-300 dark:bg-surface-600'"
                />
              </template>
            </Column>
            <!-- Shows whether season files are on disk (sizeBytes > 0) -->
            <Column header="Available">
              <template #body="{ data: s }">
                <span class="text-xs" :class="s.sizeBytes > 0 ? 'text-emerald-500' : 'text-surface-400'">
                  {{ s.sizeBytes > 0 ? 'Yes' : 'No' }}
                </span>
              </template>
            </Column>
            <!-- For never-watched shows, display 'Added' date; for watched shows, display 'Last Played' date -->
            <Column field="lastPlayed" :header="data.status === 'never' || data.status === 'never_new' ? 'Added' : 'Last Played'" sortable>
              <template #body="{ data: s }">
                {{ s.lastPlayed ? formatDate(s.lastPlayed) : (data.added ? formatDate(data.added) : '-') }}
              </template>
            </Column>
            <Column header="Episodes" sortable>
              <template #body="{ data: s }">
                <span class="tabular-nums">{{ s.totalEpisodes || '-' }}</span>
              </template>
            </Column>
            <Column field="sizeBytes" header="Size" sortable>
              <template #body="{ data: s }">
                <span class="tabular-nums">{{ formatSize(s.sizeBytes) }}</span>
              </template>
            </Column>
          </DataTable>
          <!-- Collision info: displayed when multiple Jellyfin series names mapped to the same library path -->
          <div v-if="data.collidingNames?.length" class="mt-2 px-3 py-2 rounded bg-orange-50 dark:bg-orange-950/30 border border-orange-200 dark:border-orange-800">
            <span class="text-xs font-medium text-orange-700 dark:text-orange-300">Collision: </span>
            <span class="text-xs text-orange-600 dark:text-orange-400">
              Multiple Jellyfin names matched this library entry:
            </span>
            <ul class="mt-1 list-disc list-inside text-xs text-orange-600 dark:text-orange-400 font-mono">
              <li v-for="name in data.collidingNames" :key="name">{{ name }}</li>
            </ul>
          </div>
          <!-- Library path (Sonarr directory) for reference -->
          <div v-if="data.libraryPath" class="mt-2 text-xs text-surface-500 font-mono">
            {{ data.libraryPath }}
          </div>
        </div>
      </template>
    </DataTable>
  </div>
</template>
