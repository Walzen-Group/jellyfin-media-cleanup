<script setup lang="ts">
import { ref, inject, type Ref } from 'vue'
import { useJobStore } from '../stores/jobStore'
import Select from 'primevue/select'
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'
import ProgressBar from './ProgressBar.vue'
import type { AnalysisRequest } from '../types/api'

const store = useJobStore()
// Injected from App.vue; prevents starting analysis without a live WebSocket connection
const wsConnected = inject<Ref<boolean>>('wsConnected', ref(false))

const modeOptions = [
  { label: 'All', value: 'all' },
  { label: 'Movies Only', value: 'movies' },
  { label: 'Series Only', value: 'series' },
]

// Form state: all thresholds are in months, stored as strings for input binding
const mode = ref<AnalysisRequest['mode']>('all')
const monthThreshold = ref('24')      // Items not watched in N months are cleanup candidates
const addedThreshold = ref('12')      // Never-watched items added within N months are marked "new" (not deleted)
const submitting = ref(false)         // True while the API call is in flight
const cancelling = ref(false)         // True while the cancel request is in flight

/**
 * Request job cancellation. Uses try/finally to guarantee the spinner resets
 * once the HTTP request completes, regardless of outcome. The button itself
 * disappears naturally when the WS confirms the job stopped (isAnalyzing → false).
 * Avoided using a watch for this because Vue's pre-flush order can fire it in
 * the same cycle as cancelling=true, resetting the flag before the DOM updates.
 */
async function cancel() {
  cancelling.value = true
  const showUntil = Date.now() + 1500
  try {
    await store.cancelCurrentJob()
  } finally {
    // Keep "Cancelling..." visible for at least 1.5s total
    const remaining = showUntil - Date.now()
    if (remaining > 0) {
      await new Promise(resolve => setTimeout(resolve, remaining))
    }
    cancelling.value = false
  }
}

/**
 * Submit a new analysis job with form values.
 * Converts threshold strings to numbers (with fallback defaults).
 * Sets submitting flag while the API call is in flight.
 */
async function runAnalysis() {
  submitting.value = true
  try {
    await store.startAnalysis({
      mode: mode.value,
      monthThreshold: Number(monthThreshold.value) || 24,
      addedThreshold: Number(addedThreshold.value) || 12,
    })
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="card p-5 space-y-4">
    <div class="flex flex-wrap items-end gap-4">
      <div>
        <label class="block text-xs font-medium text-surface-500 mb-1.5 uppercase tracking-wide">Mode</label>
        <Select
          v-model="mode"
          :options="modeOptions"
          option-label="label"
          option-value="value"
          class="w-40"
        />
      </div>

      <div>
        <label class="flex items-center gap-1.5 text-xs font-medium text-surface-500 mb-1.5 uppercase tracking-wide">
          Not watched since
          <i class="pi pi-info-circle text-surface-400 cursor-help" v-tooltip="'Media not watched in this many months is flagged as not recently watched'" />
        </label>
        <div class="flex items-center gap-1.5">
          <InputText v-model="monthThreshold" type="number" class="w-20" />
          <span class="text-xs text-surface-400">months</span>
        </div>
      </div>

      <div>
        <label class="flex items-center gap-1.5 text-xs font-medium text-surface-500 mb-1.5 uppercase tracking-wide">
          New if added within
          <i class="pi pi-info-circle text-surface-400 cursor-help" v-tooltip="'Items that have never been watched but were added to your library within this many months ago are considered new. Items added longer ago that remain unwatched are flagged for cleanup.'" />
        </label>
        <div class="flex items-center gap-1.5">
          <InputText v-model="addedThreshold" type="number" class="w-20" />
          <span class="text-xs text-surface-400">months</span>
        </div>
      </div>

      <!-- State machine: not running -> show Run (disabled if WS not connected). Submitting -> show spinner. Running -> show Cancel. -->
      <Button
        v-if="!store.isAnalyzing && !submitting"
        label="Run Analysis"
        icon="pi pi-play"
        :disabled="!wsConnected"
        v-tooltip="!wsConnected ? 'Waiting for WebSocket connection...' : undefined"
        @click="runAnalysis"
      />
      <Button
        v-else-if="submitting"
        label="Starting..."
        icon="pi pi-spin pi-spinner"
        disabled
      />
      <Button
        v-else
        :label="cancelling ? 'Cancelling...' : 'Cancel'"
        :icon="cancelling ? 'pi pi-spin pi-spinner' : 'pi pi-times'"
        severity="danger"
        :disabled="cancelling"
        @click="cancel"
      />
      <!-- Clear button only shown when analysis is idle and a result exists -->
      <Button
        v-if="!store.isAnalyzing && !submitting && store.currentJob?.result"
        label="Clear"
        icon="pi pi-trash"
        severity="secondary"
        text
        @click="store.clearResults()"
      />
    </div>

    <div v-if="store.error" class="text-red-500 text-sm">
      {{ store.error }}
    </div>

    <ProgressBar
      v-if="store.isAnalyzing && store.currentJob"
      :percent="store.currentJob.progressPercent"
      :step="store.currentJob.progressStep"
      :step-index="store.currentJob.stepIndex"
      :total-steps="store.currentJob.totalSteps"
    />
  </div>
</template>
