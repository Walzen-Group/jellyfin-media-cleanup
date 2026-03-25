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

function tagSeries(series: { title: string; seasons: { episodeCount: number }[] }[], status: MediaStatus): SeriesRow[] {
  return series.map(s => ({
    ...s,
    status,
    totalEpisodes: s.seasons.reduce((sum, sn) => sum + sn.episodeCount, 0),
  }) as SeriesRow)
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
      ...tagMovies(r.unmatched.movies, 'unmatched'),
      ...tagMovies(r.neverWatched.movies, 'never'),
    ]
  })

  const allSeries = computed<SeriesRow[]>(() => {
    const r = currentJob.value?.result
    if (!r) return []
    const tagged = [
      ...tagSeries(r.recentlyWatched.series, 'recent'),
      ...tagSeries(r.notRecentlyWatched.series, 'old'),
      ...tagSeries(r.keep.series, 'kept'),
      ...tagSeries(r.unmatched.series, 'unmatched'),
      ...tagSeries(r.neverWatched.series, 'never'),
    ]
    // Merge rows with the same title into one, combining seasons
    const byTitle = new Map<string, SeriesRow>()
    for (const row of tagged) {
      const key = row.libraryPath || row.title
      const existing = byTitle.get(key)
      if (existing) {
        existing.seasons = [...existing.seasons, ...row.seasons]
          .sort((a, b) => a.seasonNumber - b.seasonNumber)
        existing.totalEpisodes += row.totalEpisodes
        existing.sizeBytes += row.sizeBytes
        // Derive composite status
        const statuses = new Set([existing.status, row.status])
        if (statuses.has('kept')) {
          existing.status = statuses.size > 1 ? 'mixed' : 'kept'
        } else if (statuses.has('recent') && statuses.has('old')) {
          existing.status = 'mixed'
        } else if (statuses.has('unmatched') && statuses.size > 1) {
          existing.status = 'mixed'
        }
      } else {
        byTitle.set(key, { ...row })
      }
    }
    return Array.from(byTitle.values())
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

  function handleWebSocketMessage(msg: WebSocketMessage) {
    switch (msg.type) {
      case 'job_created':
        jobs.value = [msg.job, ...jobs.value]
        break
      case 'job_progress':
        if (currentJob.value?.jobId === msg.jobId) {
          currentJob.value.status = 'running'
          currentJob.value.progressPercent = msg.percent
          currentJob.value.progressStep = msg.step
          currentJob.value.stepIndex = msg.stepIndex
          currentJob.value.totalSteps = msg.totalSteps
        }
        break
      case 'job_complete':
        if (currentJob.value?.jobId === msg.jobId) {
          currentJob.value.progressPercent = 100
          currentJob.value.completedAt = new Date().toISOString()
          error.value = null
          // Set loading before status change so the spinner shows immediately
          loading.value = true
          currentJob.value.status = 'complete'
          fetchJobResult(msg.jobId)
        }
        break
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
