import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  AnalysisRequest, FullJobResponse, JobResponse, WebSocketMessage,
  MovieRow, SeriesRow, MediaStatus,
} from '../types/api'
import { useApi } from '../composables/useApi'

/**
 * Tag movies with a status value. Used to flatten the categorized API response
 * into a single array where the status column can be filtered/sorted.
 */
function tagMovies(movies: { title: string }[], status: MediaStatus): MovieRow[] {
  return movies.map(m => ({ ...m, status }) as MovieRow)
}

export const useJobStore = defineStore('job', () => {
  const api = useApi()

  const currentJob = ref<FullJobResponse | null>(null)
  const jobs = ref<JobResponse[]>([])
  const error = ref<string | null>(null)
  const monthThreshold = ref(24)
  const loading = ref(true)

  const isAnalyzing = computed(() => {
    const s = currentJob.value?.status
    return s === 'queued' || s === 'running'
  })

  /**
   * Flatten categorized movies into a single array with status tags.
   * Allows tables to filter/sort by a single status column instead of having
   * separate tables per category. The backend categorizes for summaries and
   * the YAML report; the frontend flattens for unified table display.
   */
  const allMovies = computed<MovieRow[]>(() => {
    const r = currentJob.value?.result
    if (!r) return []
    return [
      ...tagMovies(r.recentlyWatched.movies, 'recent'),
      ...tagMovies(r.notRecentlyWatched.movies, 'old'),
      ...tagMovies(r.keep.movies, 'kept'),
      ...tagMovies(r.collision.movies, 'collision'),
      ...tagMovies(r.unmatched.movies, 'unmatched'),
      ...tagMovies(r.neverWatched.movies, 'never'),
      ...tagMovies(r.neverNew.movies, 'never_new'),
    ]
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

  async function restoreCurrentJob() {
    loading.value = true
    const minDelay = new Promise(resolve => setTimeout(resolve, 400))
    try {
      const [job] = await Promise.all([api.getCurrentJob(), minDelay])
      if (job) {
        currentJob.value = job
        error.value = null
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
    startAnalysis,
    cancelCurrentJob,
    clearResults,
    fetchJobResult,
    handleWebSocketMessage,
  }
})
