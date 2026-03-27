<script setup lang="ts">
import { ref, provide, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useJobStore } from './stores/jobStore'
import { useThemeStore } from './stores/themeStore'
import { useWebSocket } from './composables/useWebSocket'
import { useAuth } from './composables/useAuth'
import DashboardView from './views/DashboardView.vue'
import HistoryPanel from './components/HistoryPanel.vue'
import ThemeToggle from './components/ThemeToggle.vue'
import Button from 'primevue/button'
import ButtonGroup from 'primevue/buttongroup'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'

const { isAuthenticated, isAuthLoading, authEnabled, init, login, logout, loginWithToken } = useAuth()

// Token login state -- used by the master token sign-in form
const tokenInput = ref('')
const tokenLoading = ref(false)
const tokenError = ref('')

async function handleTokenLogin() {
  tokenError.value = ''
  tokenLoading.value = true
  try {
    await loginWithToken(tokenInput.value)
  } catch (e: unknown) {
    tokenError.value = e instanceof Error ? e.message : 'Invalid token'
  } finally {
    tokenLoading.value = false
  }
}

useThemeStore()
const store = useJobStore()
const { isConnected, onMessage } = useWebSocket()
onMessage((msg) => store.handleWebSocketMessage(msg))

// Provide WebSocket connection state so child components can disable actions when disconnected
provide('wsConnected', isConnected)

const gitHash = __GIT_HASH__

const { isCleanupRunning } = storeToRefs(store)
const activeView = ref<'wizard' | 'history'>('wizard')

onMounted(() => {
  init()
})
</script>

<template>
  <!-- Auth loading state -->
  <div v-if="isAuthLoading" class="min-h-screen flex items-center justify-center bg-surface-50 dark:bg-surface-950">
    <ProgressSpinner />
  </div>

  <!-- Login page (auth enabled but not authenticated) -->
  <div v-else-if="!isAuthenticated" class="min-h-screen flex items-center justify-center bg-surface-50 dark:bg-surface-950 text-surface-900 dark:text-surface-0">
    <div class="bg-surface-0 dark:bg-surface-900 rounded-xl shadow-lg p-8 max-w-sm w-full text-center">
      <h1 class="text-2xl font-bold mb-2">Jellyfin Media Cleanup</h1>
      <p class="text-surface-500 dark:text-surface-400 mb-6">Please sign in to continue</p>

      <!-- SSO login -- only shown when OIDC is configured on the backend -->
      <Button v-if="authEnabled" label="Sign in with SSO" icon="pi pi-sign-in" class="w-full" @click="login" />

      <!-- Divider between SSO and token options -->
      <div v-if="authEnabled" class="flex items-center gap-3 my-5">
        <div class="flex-1 border-t border-surface-200 dark:border-surface-700" />
        <span class="text-xs text-surface-400">or</span>
        <div class="flex-1 border-t border-surface-200 dark:border-surface-700" />
      </div>

      <!-- Master token login -- always available as an alternative -->
      <div class="flex flex-col gap-2 text-left">
        <InputText
          v-model="tokenInput"
          placeholder="Enter access token"
          type="password"
          class="w-full"
          @keyup.enter="handleTokenLogin"
        />
        <Button
          label="Sign in with token"
          icon="pi pi-key"
          severity="secondary"
          class="w-full"
          :loading="tokenLoading"
          @click="handleTokenLogin"
        />
        <!-- Token validation error message -->
        <small v-if="tokenError" class="text-red-500">{{ tokenError }}</small>
      </div>
    </div>
  </div>

  <!-- Authenticated content -->
  <div v-else class="min-h-screen bg-surface-50 dark:bg-surface-950 text-surface-900 dark:text-surface-0 transition-colors text-[15px]">
    <header class="px-3 sm:px-6 py-3.5 flex items-center justify-between bg-indigo-500/90 dark:bg-indigo-900 text-white">
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
      <div class="flex items-center gap-2 sm:gap-4">
        <!-- View toggle -->
        <ButtonGroup>
          <Button
            icon="pi pi-list"
            size="small"
            :severity="activeView === 'wizard' ? 'contrast' : 'secondary'"
            v-tooltip="'Wizard'"
            @click="activeView = 'wizard'"
          />
          <Button
            icon="pi pi-history"
            size="small"
            :severity="activeView === 'history' ? 'contrast' : 'secondary'"
            :disabled="isCleanupRunning"
            v-tooltip="isCleanupRunning ? 'Navigation locked during cleanup' : 'History'"
            @click="activeView = 'history'"
          />
        </ButtonGroup>
        <ThemeToggle />
        <Button
          v-if="authEnabled"
          icon="pi pi-sign-out"
          size="small"
          severity="secondary"
          text
          rounded
          v-tooltip="'Sign out'"
          class="!text-white hover:!bg-white/10"
          @click="logout"
        />
        <span class="text-xs text-indigo-300/75 font-mono hidden sm:inline">{{ gitHash }}</span>
        <div class="flex items-center gap-2 text-sm text-indigo-200">
          <span
            class="inline-block w-2 h-2 rounded-full"
            :class="isConnected ? 'bg-green-500' : 'bg-red-500'"
          />
          {{ isConnected ? 'Connected' : 'Disconnected' }}
        </div>
      </div>
    </header>

    <main class="mx-auto px-2 sm:px-6 py-4 sm:py-6 w-full sm:w-[90%]">
      <Message
        v-if="isCleanupRunning"
        severity="warn"
        :closable="false"
        class="mb-4"
      >
        Cleanup in progress -- navigation is locked until complete.
      </Message>
      <DashboardView v-if="activeView === 'wizard'" />
      <HistoryPanel v-else />
    </main>
  </div>
</template>
