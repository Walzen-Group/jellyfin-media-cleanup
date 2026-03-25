import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  AnalysisRequest, FullJobResponse, JobResponse, WebSocketMessage,
  MovieRow, SeriesRow, MediaStatus,
} from '../types/api'
import { useApi } from '../composables/useApi'

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

  function handleWebSocketMessage(msg: WebSocketMessage) {
    switch (msg.type) {
      case 'job_created':
        jobs.value = [msg.job, ...jobs.value]
        ensureCurrentJob(msg.job.jobId)
        break
      case 'job_progress': {
        const job = ensureCurrentJob(msg.jobId)
        job.status = 'running'
        job.progressPercent = msg.percent
        job.progressStep = msg.step
        job.stepIndex = msg.stepIndex
        job.totalSteps = msg.totalSteps
        break
      }
      case 'job_complete': {
        const job = ensureCurrentJob(msg.jobId)
        job.progressPercent = 100
        job.completedAt = new Date().toISOString()
        error.value = null
        loading.value = true
        job.status = 'complete'
        fetchJobResult(msg.jobId)
        break
      }
      case 'job_cancelled':
        if (currentJob.value?.jobId === msg.jobId) {
          currentJob.value.status = 'cancelled'
          error.value = 'Analysis cancelled'
        }
        break
      case 'job_failed':
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
