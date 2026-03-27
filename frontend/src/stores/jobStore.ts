import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  AnalysisRequest, FullJobResponse, JobResponse, WebSocketMessage,
  MovieRow, SeriesRow, FilteredResult, RunPlan,
} from '../types/api'
import { useApi } from '../composables/useApi'

export const useJobStore = defineStore('job', () => {
  const api = useApi()

  const currentJob = ref<FullJobResponse | null>(null)
  const jobs = ref<JobResponse[]>([])
  const error = ref<string | null>(null)
  const monthThreshold = ref(24)
  const loading = ref(true)

  // Wizard state for the stepper UI
  const wizardStep = ref(1)
  const filteredResult = ref<FilteredResult | null>(null)
  const filterLoading = ref(false)
  const runPlan = ref<RunPlan | null>(null)
  const prepareLoading = ref(false)
  const lastFilterCategories = ref<string[]>([])
  const lastFilterGreedy = ref(false)
  const lastFilterMinSizeBytes = ref<number>(0)
  const lastFilterMaxSizeBytes = ref<number | null>(null)
  const mediaType = ref<'all' | 'movies' | 'series'>('all')

  const isAnalyzing = computed(() => {
    const s = currentJob.value?.status
    return s === 'queued' || s === 'running'
  })

  /**
   * Flatten categorized movies into a single array for unified table display.
   * Status is set by the backend on each MovieMatch, so no re-tagging needed.
   */
  const allMovies = computed<MovieRow[]>(() => {
    const r = currentJob.value?.result
    if (!r) return []
    return [
      ...r.recentlyWatched.movies,
      ...r.notRecentlyWatched.movies,
      ...r.keep.movies,
      ...r.collision.movies,
      ...r.unmatched.movies,
      ...r.neverWatched.movies,
      ...r.neverNew.movies,
    ] as MovieRow[]
  })

  /**
   * Flatten categorized series into a single array and add a computed totalEpisodes field.
   * One SeriesGroup per show (not per season) from the backend. Compute totalEpisodes by
   * summing across all seasons to display in the table. The backend already merges all
   * seasons for each show and derives a show-level status (e.g. "mixed" if seasons differ).
   */
  const allSeries = computed<SeriesRow[]>(() => {
    const r = currentJob.value?.result
    if (!r) return []
    const all = [
      ...r.recentlyWatched.series,
      ...r.notRecentlyWatched.series,
      ...r.keep.series,
      ...r.collision.series,
      ...r.unmatched.series,
      ...r.neverWatched.series,
      ...r.neverNew.series,
    ]
    return all.map(s => ({
      ...s,
      totalEpisodes: s.seasons.reduce((sum, sn) => sum + (sn.totalEpisodes || 0), 0),
    }))
  })

  /**
   * Filtered movies from the filter endpoint. Backend returns items with status already set,
   * so no tagMovies transformation is needed, just pass through.
   * Returns empty when mediaType excludes movies.
   */
  const filteredMovies = computed<MovieRow[]>(() => {
    if (mediaType.value === 'series') return []
    return (filteredResult.value?.movies ?? []) as MovieRow[]
  })

  /**
   * Filtered series from the filter endpoint. Compute totalEpisodes the same way as allSeries.
   * Returns empty when mediaType excludes series.
   */
  const filteredSeries = computed<SeriesRow[]>(() => {
    if (mediaType.value === 'movies') return []
    return (filteredResult.value?.series ?? []).map(s => ({
      ...s,
      totalEpisodes: s.seasons.reduce((sum, sn) => sum + (sn.totalEpisodes || 0), 0),
    }))
  })

  /**
   * Apply category/greedy filter to the current job's analysis result.
   * Calls the backend filter endpoint and stores the result.
   */
  async function applyFilter(categories: string[], greedy: boolean, minSizeBytes: number = 0, maxSizeBytes: number | null = null) {
    if (!currentJob.value?.jobId) return
    filterLoading.value = true
    try {
      filteredResult.value = await api.filterAnalysis(currentJob.value.jobId, { categories, greedy, mediaType: mediaType.value, minSizeBytes, maxSizeBytes })
      lastFilterCategories.value = [...categories]
      lastFilterGreedy.value = greedy
      lastFilterMinSizeBytes.value = minSizeBytes
      lastFilterMaxSizeBytes.value = maxSizeBytes
    } finally {
      filterLoading.value = false
    }
  }

  /**
   * Build a dry-run deletion plan from the current filter state.
   * Uses the same categories/greedy params that produced filteredResult.
   */
  async function prepareRunPlanAction(categories: string[], greedy: boolean) {
    if (!currentJob.value?.jobId) return
    prepareLoading.value = true
    try {
      runPlan.value = await api.prepareRunPlan(currentJob.value.jobId, {
        categories,
        greedy,
        mediaType: mediaType.value,
        minSizeBytes: lastFilterMinSizeBytes.value,
        maxSizeBytes: lastFilterMaxSizeBytes.value,
      })
    } finally {
      prepareLoading.value = false
    }
  }

  /**
   * Navigate the wizard stepper. Clears downstream state when stepping back.
   */
  function setWizardStep(step: number) {
    wizardStep.value = step
    if (step <= 2) {
      runPlan.value = null
    }
    if (step === 1) {
      filteredResult.value = null
    }
  }

  async function restoreCurrentJob() {
    loading.value = true
    const minDelay = new Promise(resolve => setTimeout(resolve, 400))
    try {
      const [job] = await Promise.all([api.getCurrentJob(), minDelay])
      if (job) {
        currentJob.value = job
        // Restore error message if the job had already failed (e.g. page reload after failure)
        error.value = job.status === 'failed' && job.error ? job.error : null
      }
    } finally {
      loading.value = false
    }
  }

  restoreCurrentJob()

  async function startAnalysis(request: AnalysisRequest) {
    error.value = null
    monthThreshold.value = request.monthThreshold
    try {
      const { jobId } = await api.postAnalysis(request)
      // Only initialize if WS hasn't already received and processed messages for this job.
      // Fast failures (e.g. bad API key) can cause job_failed to arrive before the HTTP
      // response resolves, and unconditionally overwriting here would bury the error.
      if (currentJob.value?.jobId !== jobId) {
        currentJob.value = {
          jobId,
          status: 'queued',
          progressPercent: 0,
          progressStep: 'Queued',
          stepIndex: 0,
          totalSteps: 0,
          createdAt: new Date().toISOString(),
          completedAt: null,
          error: null,
        }
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to start analysis'
    }
  }

  async function cancelCurrentJob() {
    if (!currentJob.value) return
    try {
      await api.cancelJob(currentJob.value.jobId)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to cancel job'
      // Force a non-analyzing status so isAnalyzing goes false and the cancel
      // button unsticks (e.g. when the job no longer exists on the server).
      if (currentJob.value) currentJob.value.status = 'cancelled'
    }
  }

  async function fetchJobResult(jobId: string) {
    loading.value = true
    try {
      currentJob.value = await api.getJob(jobId)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch job result'
    } finally {
      loading.value = false
    }
  }

  /**
   * Ensure currentJob is set to the given jobId (create if needed).
   * Used by WebSocket message handlers to guarantee currentJob exists
   * before updating its fields. Returns the (now current) job object.
   */
  function ensureCurrentJob(jobId: string): FullJobResponse {
    if (currentJob.value?.jobId !== jobId) {
      currentJob.value = {
        jobId,
        status: 'running',
        progressPercent: 0,
        progressStep: '',
        stepIndex: 0,
        totalSteps: 0,
        createdAt: new Date().toISOString(),
        completedAt: null,
        error: null,
      }
    }
    return currentJob.value!
  }

  /**
   * Handle WebSocket messages from the backend. Updates currentJob state based on
   * the message type. On job_complete, fetches the full result (with AnalysisResult).
   * For progress messages, updates the progress bar fields in real time.
   */
  function handleWebSocketMessage(msg: WebSocketMessage) {
    switch (msg.type) {
      case 'job_created':
        // Add to jobs list (prepend for recency) and make it current
        jobs.value = [msg.job, ...jobs.value]
        ensureCurrentJob(msg.job.jobId)
        break
      case 'job_progress': {
        // Update current job with live progress data (no result yet)
        const job = ensureCurrentJob(msg.jobId)
        job.status = 'running'
        job.progressPercent = msg.percent
        job.progressStep = msg.step
        job.stepIndex = msg.stepIndex
        job.totalSteps = msg.totalSteps
        break
      }
      case 'job_complete': {
        // Mark as complete and fetch full result (which includes AnalysisResult)
        const job = ensureCurrentJob(msg.jobId)
        job.progressPercent = 100
        job.completedAt = new Date().toISOString()
        error.value = null
        loading.value = true
        job.status = 'complete'
        fetchJobResult(msg.jobId)  // Loads job.result with AnalysisResult
        break
      }
      case 'job_cancelled':
        // Update current job if it matches
        if (currentJob.value?.jobId === msg.jobId) {
          currentJob.value.status = 'cancelled'
          error.value = 'Analysis cancelled'
        }
        break
      case 'job_failed':
        // Update current job with error details
        if (currentJob.value?.jobId === msg.jobId) {
          currentJob.value.status = 'failed'
          currentJob.value.error = msg.error
          error.value = msg.error ?? 'Analysis failed'
        }
        break
    }
  }

  async function clearResults() {
    try {
      await api.clearResults()
      currentJob.value = null
      error.value = null
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to clear results'
    }
  }

  return {
    currentJob,
    jobs,
    isAnalyzing,
    loading,
    error,
    monthThreshold,
    allMovies,
    allSeries,
    wizardStep,
    filteredResult,
    filterLoading,
    filteredMovies,
    filteredSeries,
    runPlan,
    prepareLoading,
    lastFilterCategories,
    lastFilterGreedy,
    lastFilterMinSizeBytes,
    lastFilterMaxSizeBytes,
    mediaType,
    applyFilter,
    prepareRunPlan: prepareRunPlanAction,
    setWizardStep,
    startAnalysis,
    cancelCurrentJob,
    clearResults,
    fetchJobResult,
    handleWebSocketMessage,
  }
})
