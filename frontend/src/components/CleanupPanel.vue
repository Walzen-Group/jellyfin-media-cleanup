<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useJobStore } from '../stores/jobStore'
import { useApi } from '../composables/useApi'
import { formatSize } from '../utils/format'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import ToggleSwitch from 'primevue/toggleswitch'
import ProgressBar from './ProgressBar.vue'
import Tag from 'primevue/tag'

const store = useJobStore()
const api = useApi()

const {
  isCleanupRunning, cleanupTotalItems, cleanupLog,
  cleanupReport, cleanupJobId, cleanupSimulate,
  selectedMovieDeletions, selectedFullSeriesDeletions, selectedSeasonCleanups,
} = storeToRefs(store)

const simulate = ref(true)
const showDialog1 = ref(false)
const showDialog2 = ref(false)
const confirmPhrase = ref('')

const CONFIRM_PHRASE = 'Yes, I am sure and I really want to perform this action'

const progressPercent = computed(() => {
  if (cleanupTotalItems.value === 0) return 0
  return Math.round((cleanupLog.value.length / cleanupTotalItems.value) * 100)
})

/** Summary computed from user's PreparePanel selections (not the full backend plan) */
const selectionSummary = computed(() => {
  const movieCount = selectedMovieDeletions.value.length
  const fullSeriesCount = selectedFullSeriesDeletions.value.length
  const seasonCleanupCount = selectedSeasonCleanups.value.length
  const movieSize = selectedMovieDeletions.value.reduce((sum, m) => sum + m.sizeBytes, 0)
  const seriesSize = selectedFullSeriesDeletions.value.reduce((sum, s) => sum + s.sizeBytes, 0)
  const seasonSize = selectedSeasonCleanups.value.reduce((sum, s) => sum + s.totalSizeBytes, 0)
  const totalSize = movieSize + seriesSize + seasonSize
  if (movieCount === 0 && fullSeriesCount === 0 && seasonCleanupCount === 0) return null
  return {
    movieCount,
    fullSeriesCount,
    seasonCleanupCount,
    totalItems: movieCount + fullSeriesCount + seasonCleanupCount,
    totalSizeFmt: formatSize(totalSize),
  }
})

const confirmPhraseMatches = computed(() => confirmPhrase.value === CONFIRM_PHRASE)

function openConfirm() {
  showDialog1.value = true
}

function proceedToDialog2() {
  showDialog1.value = false
  confirmPhrase.value = ''
  showDialog2.value = true
}

async function confirmExecute() {
  showDialog2.value = false
  await store.executeCleanup(simulate.value)
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

function mediaTypeSeverity(mt: string): 'success' | 'danger' | 'warn' | 'secondary' | 'info' {
  switch (mt) {
    case 'movie': return 'info'
    case 'series': return 'success'
    case 'season': return 'warn'
    default: return 'secondary'
  }
}

function backToAnalysis() {
  store.clearResults()
  store.setWizardStep(1)
}

// Track download state so the button can show a spinner and errors can surface
const downloadError = ref<string | null>(null)
const isDownloading = ref(false)

/**
 * Fetch the YAML report as a Blob via the auth-bearing API wrapper, then
 * trigger a browser download. Using fetch (not window.location.href) is
 * required so the Authorization header is included - direct navigation
 * cannot carry custom headers and results in a 401.
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

onMounted(() => {
  store.fetchCleanupCurrent()
})
</script>

<template>
  <div class="space-y-4">

    <!-- Pre-execution state -->
    <template v-if="!isCleanupRunning && !cleanupReport">
      <div class="card p-5 space-y-5">
        <div class="flex items-center gap-3">
          <Button
            label="Back"
            icon="pi pi-arrow-left"
            severity="secondary"
            @click="store.setWizardStep(3)"
          />
          <h2 class="text-lg font-semibold">Execute Cleanup</h2>
        </div>

        <!-- Selection summary from PreparePanel -->
        <div v-if="selectionSummary" class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div class="rounded-lg bg-surface-100 dark:bg-surface-800 p-3 text-center stagger-in" style="--stagger-index: 0">
            <div class="text-2xl font-semibold tracking-tight tabular-nums text-primary-500">{{ selectionSummary.movieCount }}</div>
            <div class="text-xs text-surface-500 mt-1">Movies</div>
          </div>
          <div class="rounded-lg bg-surface-100 dark:bg-surface-800 p-3 text-center stagger-in" style="--stagger-index: 1">
            <div class="text-2xl font-semibold tracking-tight tabular-nums text-primary-500">{{ selectionSummary.fullSeriesCount }}</div>
            <div class="text-xs text-surface-500 mt-1">Full Series</div>
          </div>
          <div class="rounded-lg bg-surface-100 dark:bg-surface-800 p-3 text-center stagger-in" style="--stagger-index: 2">
            <div class="text-2xl font-semibold tracking-tight tabular-nums text-primary-500">{{ selectionSummary.seasonCleanupCount }}</div>
            <div class="text-xs text-surface-500 mt-1">Season Cleanups</div>
          </div>
          <div class="rounded-lg bg-surface-100 dark:bg-surface-800 p-3 text-center stagger-in" style="--stagger-index: 3">
            <div class="text-2xl font-semibold tracking-tight tabular-nums text-orange-500">{{ selectionSummary.totalSizeFmt }}</div>
            <div class="text-xs text-surface-500 mt-1">Total Size</div>
          </div>
        </div>

        <div v-else class="text-surface-400 text-sm">
          No selection available. Complete Step 3 (Prepare) first.
        </div>

        <!-- Simulate toggle -->
        <div class="flex items-center gap-3">
          <ToggleSwitch v-model="simulate" inputId="simulate-toggle" />
          <label for="simulate-toggle" class="text-sm font-medium cursor-pointer">
            Simulate deletion (dry run)
            <span class="text-surface-400 font-normal ml-1">- no actual files will be deleted</span>
          </label>
        </div>

        <Transition name="fade-slide">
          <div v-if="!simulate" class="flex items-start gap-2 text-sm text-orange-600 dark:text-orange-400">
            <i class="pi pi-exclamation-triangle mt-0.5 shrink-0" />
            <span>Simulation mode is OFF. Files will be permanently deleted via Radarr/Sonarr APIs.</span>
          </div>
        </Transition>

        <div class="flex gap-3">
          <Button
            label="Execute Cleanup"
            icon="pi pi-trash"
            severity="danger"
            :disabled="!selectionSummary"
            @click="openConfirm"
          />
        </div>
      </div>
    </template>

    <!-- During execution -->
    <template v-else-if="isCleanupRunning">
      <div class="card p-5 space-y-4">
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">
            {{ cleanupSimulate ? 'Simulating' : 'Executing' }} Cleanup
          </h2>
          <Button
            label="Cancel"
            icon="pi pi-times"
            severity="secondary"
            size="small"
            @click="store.cancelCleanup()"
          />
        </div>

        <div>
          <div class="text-sm text-surface-500 mb-2">
            Deleting item {{ cleanupLog.length }} of {{ cleanupTotalItems }}
          </div>
          <ProgressBar
            :percent="progressPercent"
            :step="cleanupLog.length > 0 ? cleanupLog[cleanupLog.length - 1].title : 'Starting...'"
            :step-index="cleanupLog.length"
            :total-steps="cleanupTotalItems"
          />
        </div>

        <!-- Real-time log -->
        <div class="overflow-y-auto max-h-[400px] space-y-1 rounded border border-surface-200 dark:border-surface-700 p-2">
          <div
            v-for="(entry, i) in cleanupLog"
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
            <!-- sizeBytes is absent on live WS progress entries - only present on completed report entries -->
            <span v-if="entry.sizeBytes != null" class="text-surface-400 text-xs shrink-0">{{ formatSize(entry.sizeBytes) }}</span>
            <Tag :value="entry.status" :severity="statusSeverity(entry.status)" class="shrink-0 text-xs" />
          </div>
          <div v-if="cleanupLog.length === 0" class="text-surface-400 text-sm text-center py-4">
            Waiting for first item...
          </div>
        </div>
      </div>
    </template>

    <!-- After completion -->
    <template v-else-if="cleanupReport">
      <div class="card p-5 space-y-4">
        <div class="flex items-center gap-3">
          <h2 class="text-lg font-semibold">Cleanup Complete</h2>
          <Tag v-if="cleanupReport.simulate" value="Simulated" severity="warn" />
        </div>

        <!-- Summary stats -->
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
            <div class="text-xs text-surface-500 mt-1">Items Processed</div>
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

        <!-- Download error shown inline below the buttons so it doesn't lose context -->
        <div v-if="downloadError" class="text-sm text-red-500 flex items-center gap-1.5">
          <i class="pi pi-exclamation-circle shrink-0" />
          {{ downloadError }}
        </div>

        <div class="flex gap-3">
          <Button
            :label="isDownloading ? 'Downloading...' : 'Download Report (YAML)'"
            :icon="isDownloading ? 'pi pi-spin pi-spinner' : 'pi pi-download'"
            severity="secondary"
            :disabled="isDownloading"
            @click="downloadReport"
          />
          <Button
            label="Back to Analysis"
            icon="pi pi-arrow-left"
            severity="secondary"
            text
            @click="backToAnalysis"
          />
        </div>
      </div>
    </template>

    <!-- Dialog 1: initial confirmation -->
    <Dialog v-model:visible="showDialog1" header="Confirm Cleanup" modal :style="{ width: '480px' }">
      <div class="space-y-4 text-sm">
        <p>
          You are about to
          <strong>{{ simulate ? 'simulate deletion of ' : 'permanently delete ' }}</strong>
          <template v-if="selectionSummary">
            <strong> {{ selectionSummary.totalItems }} items</strong>
            ({{ selectionSummary.totalSizeFmt }}).
          </template>
          <template v-else>
            the selected media.
          </template>
        </p>
        <p v-if="!simulate" class="text-orange-600 dark:text-orange-400">
          This will call the Radarr/Sonarr APIs and delete files from disk.
        </p>
      </div>
      <template #footer>
        <Button label="Cancel" severity="secondary" text @click="showDialog1 = false" />
        <Button label="Yes, proceed" icon="pi pi-arrow-right" iconPos="right" @click="proceedToDialog2" />
      </template>
    </Dialog>

    <!-- Dialog 2: type-to-confirm -->
    <Dialog v-model:visible="showDialog2" header="Final Confirmation" modal :style="{ width: '520px' }">
      <div class="space-y-4 text-sm">
        <p>This cannot be undone. Type the following phrase exactly to confirm:</p>
        <code class="block bg-surface-100 dark:bg-surface-800 rounded p-2 text-xs select-all break-words">
          {{ CONFIRM_PHRASE }}
        </code>
        <InputText
          v-model="confirmPhrase"
          class="w-full"
          placeholder="Type the phrase above..."
          autofocus
          @keyup.enter="confirmPhraseMatches && confirmExecute()"
        />
      </div>
      <template #footer>
        <Button label="Cancel" severity="secondary" text @click="showDialog2 = false" />
        <Button
          label="Confirm"
          severity="danger"
          icon="pi pi-trash"
          :disabled="!confirmPhraseMatches"
          @click="confirmExecute"
        />
      </template>
    </Dialog>

  </div>
</template>
