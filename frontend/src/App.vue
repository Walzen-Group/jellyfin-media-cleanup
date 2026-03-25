<script setup lang="ts">
import { useJobStore } from './stores/jobStore'
import { useThemeStore } from './stores/themeStore'
import { useWebSocket } from './composables/useWebSocket'
import DashboardView from './views/DashboardView.vue'
import ThemeToggle from './components/ThemeToggle.vue'

useThemeStore()
const store = useJobStore()
const { isConnected, onMessage } = useWebSocket()
onMessage((msg) => store.handleWebSocketMessage(msg))
</script>

<template>
  <div class="min-h-screen bg-surface-50 dark:bg-surface-950 text-surface-900 dark:text-surface-0 transition-colors text-[15px]">
    <header class="px-6 py-3.5 flex items-center justify-between bg-indigo-500/90 dark:bg-indigo-900 text-white">
      <h1 class="flex items-center gap-2.5 text-lg font-semibold tracking-wide">
        <svg width="20" height="18" viewBox="0 0 20 18" fill="currentColor" class="shrink-0 opacity-90 -mb-0.5">
          <rect x="3" y="0" width="14" height="6" rx="1.5" />
          <rect x="0" y="5" width="20" height="7" rx="1.5" />
          <circle cx="5" cy="15.5" r="1.3" />
          <circle cx="9" cy="15.5" r="1.3" />
          <circle cx="14" cy="15.5" r="1.3" />
        </svg>
        Wedia Cleanup
      </h1>
      <div class="flex items-center gap-4">
        <ThemeToggle />
        <div class="flex items-center gap-2 text-sm text-indigo-200">
          <span
            class="inline-block w-2 h-2 rounded-full"
            :class="isConnected ? 'bg-green-500' : 'bg-red-500'"
          />
          {{ isConnected ? 'Connected' : 'Disconnected' }}
        </div>
      </div>
    </header>
    <main class="mx-auto px-6 py-6 w-[90%]">
      <DashboardView />
    </main>
  </div>
</template>
