<script setup lang="ts">
import { ref } from 'vue'
import { useJobStore } from '../stores/jobStore'
import Select from 'primevue/select'
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'
import ProgressBar from './ProgressBar.vue'
import type { AnalysisRequest } from '../types/api'

const store = useJobStore()

const modeOptions = [
  { label: 'All', value: 'all' },
  { label: 'Movies Only', value: 'movies' },
  { label: 'Series Only', value: 'series' },
]

const mode = ref<AnalysisRequest['mode']>('series')
const monthThreshold = ref('24')
const submitting = ref(false)

async function runAnalysis() {
  submitting.value = true
  try {
    await store.startAnalysis({ mode: mode.value, monthThreshold: Number(monthThreshold.value) || 24 })
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
        <label class="block text-xs font-medium text-surface-500 mb-1.5 uppercase tracking-wide">Months</label>
        <InputText
          v-model="monthThreshold"
          type="number"
          class="w-20"
        />
      </div>

      <Button
        v-if="!store.isAnalyzing && !submitting"
        label="Run Analysis"
        icon="pi pi-play"
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
        label="Cancel"
        icon="pi pi-times"
        severity="danger"
        @click="store.cancelCurrentJob()"
      />
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
