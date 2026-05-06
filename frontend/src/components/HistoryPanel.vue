<!--
  HistoryPanel.vue
  Two-tab panel: (1) Deletion History with server-side pagination + title search,
  (2) Last Report with download button.

  Pagination strategy: PrimeVue Paginator component (server-side). Each page
  change fires a new API request. The search input is debounced ~250ms; typing
  resets offset to 0 so the user always sees results from the first page.
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useJobStore } from '../stores/jobStore'
import { useApi } from '../composables/useApi'
import { formatSize, formatDate } from '../utils/format'
import type { HistoryEntry } from '../types/api'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanels from 'primevue/tabpanels'
import TabPanel from 'primevue/tabpanel'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import Paginator from 'primevue/paginator'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'

const store = useJobStore()
const api = useApi()
const { cleanupReport, cleanupJobId } = storeToRefs(store)

// --- Reactive history data ---

/** Current page of entries returned by the API */
const historyEntries = ref<HistoryEntry[]>([])

/** Total matching records as reported by the API (used for paginator) */
const historyTotal = ref(0)

/** Multi-select state for bulk delete */
const selectedEntries = ref<HistoryEntry[]>([])

/** Loading flag for all history operations */
const historyLoading = ref(false)

/** Error message shown inline above the table */
const historyError = ref<string | null>(null)

// --- Pagination state ---

/** Current page (zero-based offset = first * page). PrimeVue Paginator uses 0-based first. */
const pageFirst = ref(0)

/** Page size options exposed to the user */
const pageSizeOptions = [
  { label: '50 per page', value: 50 },
  { label: '100 per page', value: 100 },
  { label: '200 per page', value: 200 },
  { label: '500 per page', value: 500 },
]

/** Currently selected page size */
const pageSize = ref(50)

// --- Search state ---

/** Raw value of the search input (bound directly to InputText) */
const searchRaw = ref('')

/** The debounced query actually sent to the API. Updated after ~250ms idle. */
const searchQuery = ref('')

/** Timer ID for the debounce on searchRaw */
let debounceTimer: ReturnType<typeof setTimeout> | null = null

/** Whether a search query is active (drives the empty-state message variant) */
const isFiltered = computed(() => searchQuery.value.trim().length > 0)

/** Whether the paginator should be visible (only when total exceeds page size) */
const showPaginator = computed(() => historyTotal.value > pageSize.value)

// --- Dialog state ---

const showDeleteSelectedDialog = ref(false)
const showClearAllDialog = ref(false)

// --- Helpers ---

function mediaTypeSeverity(mt: string): 'success' | 'danger' | 'warn' | 'secondary' | 'info' {
  switch (mt) {
    case 'movie': return 'info'
    case 'series': return 'success'
    case 'season': return 'warn'
    default: return 'secondary'
  }
}

function statusSeverity(status: string): 'success' | 'danger' | 'warn' | 'secondary' | 'info' {
  switch (status) {
    case 'deleted': return 'success'
    case 'simulated': return 'info'
    case 'failed': return 'danger'
    case 'skipped': return 'warn'
    default: return 'secondary'
  }
}

// --- API integration ---

/**
 * Fetch one page of history from the server using current pagination/search state.
 * Does not reset pageFirst - callers are responsible for resetting before calling
 * when a search or page-size change requires returning to the first page.
 */
async function loadHistory() {
  historyLoading.value = true
  historyError.value = null
  try {
    const result = await api.getCleanupHistory(pageSize.value, pageFirst.value, searchQuery.value)
    historyEntries.value = result.items
    historyTotal.value = result.total
  } catch (e) {
    historyError.value = e instanceof Error ? e.message : 'Failed to load history'
  } finally {
    historyLoading.value = false
  }
}

/**
 * Handle the search input with a 250ms debounce.
 * Resets to page 0 so the user always sees results from the beginning.
 */
function onSearchInput(value: string) {
  if (debounceTimer !== null) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    searchQuery.value = value
    // Reset to first page whenever the query changes
    pageFirst.value = 0
    loadHistory()
  }, 250)
}

/**
 * Clear the search field and reload from page 0.
 */
function clearSearch() {
  searchRaw.value = ''
  searchQuery.value = ''
  pageFirst.value = 0
  loadHistory()
}

/**
 * Called by PrimeVue Paginator's @page event.
 * event.first is the zero-based index of the first row on the new page.
 */
function onPageChange(event: { first: number; rows: number }) {
  pageFirst.value = event.first
  loadHistory()
}

/**
 * Called when the user picks a different page size.
 * Resets to page 0 so we don't land on an out-of-range offset.
 */
function onPageSizeChange() {
  pageFirst.value = 0
  loadHistory()
}

// --- Mutation operations ---

async function deleteSelected() {
  showDeleteSelectedDialog.value = false
  historyLoading.value = true
  try {
    await Promise.all(selectedEntries.value.map(e => api.deleteHistoryEntry(e.id)))
    selectedEntries.value = []
    // After deletion the total shrinks; stay on same page (loadHistory resets if needed)
    await loadHistory()
  } catch (e) {
    historyError.value = e instanceof Error ? e.message : 'Failed to delete entries'
    historyLoading.value = false
  }
}

async function clearAll() {
  showClearAllDialog.value = false
  historyLoading.value = true
  try {
    await api.clearCleanupHistory()
    store.hasCleanupHistory = false
    selectedEntries.value = []
    pageFirst.value = 0
    await loadHistory()
  } catch (e) {
    historyError.value = e instanceof Error ? e.message : 'Failed to clear history'
    historyLoading.value = false
  }
}

// --- Download (Last Report tab) ---

/** Error shown inline in the Last Report tab when the download fails */
const downloadError = ref<string | null>(null)

/** True while the YAML blob is being fetched */
const isDownloading = ref(false)

/**
 * Fetch the YAML report as a Blob via the auth-bearing API wrapper, then
 * trigger a browser download. Direct navigation via window.location.href
 * cannot attach an Authorization header, which causes a 401 on protected
 * endpoints. The fetch approach routes through the same token path used
 * by all other API calls.
 */
async function downloadReport() {
  if (!cleanupJobId.value) return
  downloadError.value = null
  isDownloading.value = true
  try {
    const blob = await api.fetchCleanupReportBlob(cleanupJobId.value)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `cleanup-report-${cleanupJobId.value}.yaml`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (e) {
    downloadError.value = e instanceof Error ? e.message : 'Download failed'
  } finally {
    isDownloading.value = false
  }
}

onMounted(loadHistory)
</script>

<template>
  <div>
    <Tabs value="history">
      <TabList>
        <Tab value="history">
          <i class="pi pi-database mr-1.5" />
          Deletion History
        </Tab>
        <Tab value="report">
          <i class="pi pi-file-o mr-1.5" />
          Last Report
        </Tab>
      </TabList>
      <TabPanels>

        <!-- History tab -->
        <TabPanel value="history">
          <div class="space-y-3 pt-3">
            <!-- Inline error with retry -->
            <Message v-if="historyError" severity="error" :closable="false">
              {{ historyError }}
              <Button label="Retry" icon="pi pi-refresh" severity="secondary" size="small" text class="ml-2" @click="loadHistory" />
            </Message>

            <!-- Toolbar: search + bulk actions + page-size selector + refresh -->
            <div class="flex flex-wrap items-center gap-2">
              <!-- Title search with clear button -->
              <div class="relative flex-1 min-w-[180px] max-w-xs">
                <InputText
                  v-model="searchRaw"
                  placeholder="Filter by title..."
                  size="small"
                  class="w-full pr-7"
                  @input="onSearchInput(($event.target as HTMLInputElement).value)"
                />
                <!-- Clear icon - only visible when something is typed -->
                <button
                  v-if="searchRaw"
                  class="absolute right-2 top-1/2 -translate-y-1/2 text-surface-400 hover:text-surface-600 dark:hover:text-surface-200 transition-colors"
                  aria-label="Clear search"
                  @click="clearSearch"
                >
                  <i class="pi pi-times text-xs" />
                </button>
              </div>

              <!-- Page size selector -->
              <Select
                v-model="pageSize"
                :options="pageSizeOptions"
                option-label="label"
                option-value="value"
                size="small"
                class="w-36"
                @change="onPageSizeChange"
              />

              <!-- Bulk delete -->
              <Button
                label="Delete selected"
                icon="pi pi-trash"
                severity="secondary"
                size="small"
                :disabled="selectedEntries.length === 0"
                @click="showDeleteSelectedDialog = true"
              />

              <!-- Clear all -->
              <Button
                label="Clear all"
                icon="pi pi-times"
                severity="danger"
                size="small"
                :disabled="historyTotal === 0"
                @click="showClearAllDialog = true"
              />

              <!-- Refresh spinner button -->
              <Button
                :icon="historyLoading ? 'pi pi-spin pi-spinner' : 'pi pi-refresh'"
                severity="secondary"
                text
                size="small"
                :disabled="historyLoading"
                @click="loadHistory"
              />

              <!-- "X of Y" counter - always shows current page count / total -->
              <span class="text-xs text-surface-400 ml-auto whitespace-nowrap">
                <!-- Show count of entries on the current page vs total matching records -->
                {{ historyEntries.length }} of {{ historyTotal }} entries
              </span>
            </div>

            <!--
              DataTable: server-side pagination, so we disable the built-in
              client-side paginator (paginator prop omitted). We render our
              own PrimeVue Paginator below for full control over server calls.
            -->
            <DataTable
              v-model:selection="selectedEntries"
              :value="historyEntries"
              :loading="historyLoading"
              selection-mode="multiple"
              data-key="id"
              size="small"
              striped-rows
            >
              <!-- Empty state: differentiate between "no data at all" and "no search results" -->
              <template #empty>
                <div class="flex flex-col items-center justify-center gap-2 py-8 text-surface-400">
                  <i class="pi pi-search text-3xl" />
                  <template v-if="isFiltered">
                    <!-- Filtered empty state: tell user what they searched for -->
                    <p class="text-sm">No history matching <span class="font-semibold text-surface-500">"{{ searchQuery }}"</span></p>
                    <Button label="Clear search" severity="secondary" size="small" text @click="clearSearch" />
                  </template>
                  <template v-else>
                    <!-- Generic empty state: no history yet -->
                    <p class="text-sm">No deletion history yet.</p>
                    <p class="text-xs">Run a cleanup to populate this list.</p>
                  </template>
                </div>
              </template>

              <Column selection-mode="multiple" header-style="width: 3rem" />
              <Column field="mediaType" header="Type" style="width: 90px">
                <template #body="{ data }">
                  <Tag :value="data.mediaType" :severity="mediaTypeSeverity(data.mediaType)" class="text-xs" />
                </template>
              </Column>
              <Column field="title" header="Title">
                <template #body="{ data }">
                  <span class="font-medium">{{ data.title }}</span>
                </template>
              </Column>
              <Column field="path" header="Path" class="font-mono text-xs text-surface-500" />
              <Column field="seasonNumbers" header="Seasons" style="width: 100px">
                <template #body="{ data }">
                  {{ data.seasonNumbers?.join(', ') || '-' }}
                </template>
              </Column>
              <Column field="sizeBytes" header="Size" style="width: 100px">
                <template #body="{ data }">{{ formatSize(data.sizeBytes) }}</template>
              </Column>
              <Column field="deletedAt" header="Deleted At" style="width: 120px">
                <template #body="{ data }">{{ formatDate(data.deletedAt) }}</template>
              </Column>
              <Column field="simulated" header="Mode" style="width: 100px">
                <template #body="{ data }">
                  <Tag
                    :value="data.simulated ? 'Simulated' : 'Real'"
                    :severity="data.simulated ? 'warn' : 'success'"
                    class="text-xs"
                  />
                </template>
              </Column>
            </DataTable>

            <!--
              Server-side Paginator: only visible when total exceeds the page size.
              @page fires with { first, rows, page, pageCount } - we use first (row offset).
            -->
            <Paginator
              v-if="showPaginator"
              :first="pageFirst"
              :rows="pageSize"
              :total-records="historyTotal"
              :rows-per-page-options="[]"
              template="FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink"
              @page="onPageChange"
            />
          </div>
        </TabPanel>

        <!-- Last Report tab -->
        <TabPanel value="report">
          <div class="pt-4 space-y-4">
            <template v-if="cleanupReport">
              <!-- Summary cards -->
              <div class="flex items-center gap-3">
                <h3 class="text-base font-semibold">Last Cleanup Report</h3>
                <Tag v-if="cleanupReport.simulate" value="Simulated" severity="warn" />
              </div>

              <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div class="rounded-lg bg-surface-100 dark:bg-surface-800 p-3 text-center stagger-in" style="--stagger-index: 0">
                  <div class="text-2xl font-semibold tracking-tight tabular-nums text-green-500">{{ cleanupReport.deletedCount }}</div>
                  <div class="text-xs text-surface-500 mt-1">{{ cleanupReport.simulate ? 'Simulated' : 'Deleted' }}</div>
                </div>
                <div class="rounded-lg bg-surface-100 dark:bg-surface-800 p-3 text-center stagger-in" style="--stagger-index: 1">
                  <div class="text-2xl font-semibold tracking-tight tabular-nums" :class="cleanupReport.failedCount > 0 ? 'text-red-500' : 'text-surface-400'">
                    {{ cleanupReport.failedCount }}
                  </div>
                  <div class="text-xs text-surface-500 mt-1">Failed</div>
                </div>
                <div class="rounded-lg bg-surface-100 dark:bg-surface-800 p-3 text-center stagger-in" style="--stagger-index: 2">
                  <div class="text-2xl font-semibold tracking-tight tabular-nums text-primary-500">{{ cleanupReport.totalSizeFmt }}</div>
                  <div class="text-xs text-surface-500 mt-1">Total Size</div>
                </div>
                <div class="rounded-lg bg-surface-100 dark:bg-surface-800 p-3 text-center stagger-in" style="--stagger-index: 3">
                  <div class="text-2xl font-semibold tracking-tight tabular-nums text-surface-500">{{ cleanupReport.entries.length }}</div>
                  <div class="text-xs text-surface-500 mt-1">Items</div>
                </div>
              </div>

              <!-- Entry log -->
              <div class="overflow-y-auto max-h-[400px] space-y-1 rounded border border-surface-200 dark:border-surface-700 p-2">
                <div
                  v-for="(entry, i) in cleanupReport.entries"
                  :key="i"
                  class="flex items-center gap-2 py-1 px-1 text-sm"
                >
                  <i
                    class="shrink-0"
                    :class="{
                      'pi pi-check-circle text-green-500': entry.status === 'deleted' || entry.status === 'simulated',
                      'pi pi-times-circle text-red-500': entry.status === 'failed',
                      'pi pi-minus-circle text-surface-400': entry.status === 'skipped',
                    }"
                  />
                  <span class="flex-1 truncate" :title="entry.title">{{ entry.title }}</span>
                  <Tag :value="entry.mediaType" :severity="mediaTypeSeverity(entry.mediaType)" class="shrink-0 text-xs" />
                  <span class="text-surface-400 text-xs shrink-0">{{ formatSize(entry.sizeBytes ?? 0) }}</span>
                  <Tag :value="entry.status" :severity="statusSeverity(entry.status)" class="shrink-0 text-xs" />
                </div>
              </div>

              <!-- Download error shown inline so the user sees it without losing tab context -->
              <div v-if="downloadError" class="text-sm text-red-500 flex items-center gap-1.5">
                <i class="pi pi-exclamation-circle shrink-0" />
                {{ downloadError }}
              </div>

              <Button
                :label="isDownloading ? 'Downloading...' : 'Download Report (YAML)'"
                :icon="isDownloading ? 'pi pi-spin pi-spinner' : 'pi pi-download'"
                severity="secondary"
                :disabled="isDownloading"
                @click="downloadReport"
              />
            </template>

            <!-- No report yet -->
            <div v-else class="card p-10 flex flex-col items-center justify-center text-center text-surface-400 space-y-2">
              <i class="pi pi-file-o text-4xl" />
              <p>No cleanup report available.</p>
              <p class="text-sm">Run a cleanup to generate a report.</p>
            </div>
          </div>
        </TabPanel>

      </TabPanels>
    </Tabs>

    <!-- Delete selected confirm dialog -->
    <Dialog v-model:visible="showDeleteSelectedDialog" header="Delete Selected Entries" modal :style="{ width: '400px' }">
      <p class="text-sm">Remove {{ selectedEntries.length }} selected entries from the deletion history?</p>
      <template #footer>
        <Button label="Cancel" severity="secondary" text @click="showDeleteSelectedDialog = false" />
        <Button label="Delete" severity="danger" icon="pi pi-trash" @click="deleteSelected" />
      </template>
    </Dialog>

    <!-- Clear all confirm dialog -->
    <Dialog v-model:visible="showClearAllDialog" header="Clear All History" modal :style="{ width: '400px' }">
      <p class="text-sm">This will permanently remove all {{ historyTotal }} deletion history entries. This cannot be undone.</p>
      <template #footer>
        <Button label="Cancel" severity="secondary" text @click="showClearAllDialog = false" />
        <Button label="Clear All" severity="danger" icon="pi pi-trash" @click="clearAll" />
      </template>
    </Dialog>
  </div>
</template>
