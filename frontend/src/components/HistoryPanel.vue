<script setup lang="ts">
import { ref, onMounted } from 'vue'
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

const store = useJobStore()
const api = useApi()
const { cleanupReport, cleanupJobId } = storeToRefs(store)

const historyEntries = ref<HistoryEntry[]>([])
const selectedEntries = ref<HistoryEntry[]>([])
const historyLoading = ref(false)
const historyError = ref<string | null>(null)

const showDeleteSelectedDialog = ref(false)
const showClearAllDialog = ref(false)

function mediaTypeSeverity(mt: string): 'success' | 'danger' | 'warn' | 'secondary' | 'info' {
  switch (mt) {
    case 'movie': return 'info'
    case 'series': return 'success'
    case 'season': return 'warn'
    default: return 'secondary'
  }
}

async function loadHistory() {
  historyLoading.value = true
  historyError.value = null
  try {
    historyEntries.value = await api.getCleanupHistory()
  } catch (e) {
    historyError.value = e instanceof Error ? e.message : 'Failed to load history'
  } finally {
    historyLoading.value = false
  }
}

async function deleteSelected() {
  showDeleteSelectedDialog.value = false
  historyLoading.value = true
  try {
    await Promise.all(selectedEntries.value.map(e => api.deleteHistoryEntry(e.id)))
    selectedEntries.value = []
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
    await loadHistory()
  } catch (e) {
    historyError.value = e instanceof Error ? e.message : 'Failed to clear history'
    historyLoading.value = false
  }
}

function downloadReport() {
  if (cleanupJobId.value) {
    window.location.href = api.getCleanupReportDownloadUrl(cleanupJobId.value)
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
            <Message v-if="historyError" severity="error" :closable="false">{{ historyError }}</Message>

            <!-- Toolbar -->
            <div class="flex items-center gap-2">
              <Button
                label="Delete selected"
                icon="pi pi-trash"
                severity="secondary"
                size="small"
                :disabled="selectedEntries.length === 0"
                @click="showDeleteSelectedDialog = true"
              />
              <Button
                label="Clear all"
                icon="pi pi-times"
                severity="danger"
                size="small"
                :disabled="historyEntries.length === 0"
                @click="showClearAllDialog = true"
              />
              <Button
                icon="pi pi-refresh"
                severity="secondary"
                text
                size="small"
                :loading="historyLoading"
                @click="loadHistory"
              />
              <span class="text-xs text-surface-400 ml-auto">{{ historyEntries.length }} entries</span>
            </div>

            <DataTable
              v-model:selection="selectedEntries"
              :value="historyEntries"
              :loading="historyLoading"
              selection-mode="multiple"
              data-key="id"
              size="small"
              striped-rows
              paginator
              :rows="25"
              :rows-per-page-options="[10, 25, 50]"
            >
              <Column selection-mode="multiple" header-style="width: 3rem" />
              <Column field="mediaType" header="Type" style="width: 90px">
                <template #body="{ data }">
                  <Tag :value="data.mediaType" :severity="mediaTypeSeverity(data.mediaType)" class="text-xs" />
                </template>
              </Column>
              <Column field="title" header="Title" sortable>
                <template #body="{ data }">
                  <span class="font-medium">{{ data.title }}</span>
                </template>
              </Column>
              <Column field="path" header="Path" class="font-mono text-xs text-surface-500" />
              <Column field="seasonNumbers" header="Seasons" style="width: 100px">
                <template #body="{ data }">
                  {{ data.seasonNumbers?.join(', ') || '—' }}
                </template>
              </Column>
              <Column field="sizeBytes" header="Size" sortable style="width: 100px">
                <template #body="{ data }">{{ formatSize(data.sizeBytes) }}</template>
              </Column>
              <Column field="deletedAt" header="Deleted At" sortable style="width: 120px">
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
          </div>
        </TabPanel>

        <!-- Last Report tab -->
        <TabPanel value="report">
          <div class="pt-4 space-y-4">
            <template v-if="cleanupReport">
              <!-- Summary -->
              <div class="flex items-center gap-3">
                <h3 class="text-base font-semibold">Last Cleanup Report</h3>
                <Tag v-if="cleanupReport.simulate" value="Simulated" severity="warn" />
              </div>

              <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div class="rounded-lg bg-surface-100 dark:bg-surface-800 p-3 text-center">
                  <div class="text-2xl font-bold text-green-500">{{ cleanupReport.deletedCount }}</div>
                  <div class="text-xs text-surface-500 mt-1">{{ cleanupReport.simulate ? 'Simulated' : 'Deleted' }}</div>
                </div>
                <div class="rounded-lg bg-surface-100 dark:bg-surface-800 p-3 text-center">
                  <div class="text-2xl font-bold" :class="cleanupReport.failedCount > 0 ? 'text-red-500' : 'text-surface-400'">
                    {{ cleanupReport.failedCount }}
                  </div>
                  <div class="text-xs text-surface-500 mt-1">Failed</div>
                </div>
                <div class="rounded-lg bg-surface-100 dark:bg-surface-800 p-3 text-center">
                  <div class="text-2xl font-bold text-primary-500">{{ cleanupReport.totalSizeFmt }}</div>
                  <div class="text-xs text-surface-500 mt-1">Total Size</div>
                </div>
                <div class="rounded-lg bg-surface-100 dark:bg-surface-800 p-3 text-center">
                  <div class="text-2xl font-bold text-surface-500">{{ cleanupReport.entries.length }}</div>
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
                  <span class="text-surface-400 text-xs shrink-0">{{ formatSize(entry.sizeBytes) }}</span>
                  <Tag :value="entry.status" :severity="statusSeverity(entry.status)" class="shrink-0 text-xs" />
                </div>
              </div>

              <Button
                label="Download Report (YAML)"
                icon="pi pi-download"
                severity="secondary"
                @click="downloadReport"
              />
            </template>

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
      <p class="text-sm">This will permanently remove all {{ historyEntries.length }} deletion history entries. This cannot be undone.</p>
      <template #footer>
        <Button label="Cancel" severity="secondary" text @click="showClearAllDialog = false" />
        <Button label="Clear All" severity="danger" icon="pi pi-trash" @click="clearAll" />
      </template>
    </Dialog>
  </div>
</template>
