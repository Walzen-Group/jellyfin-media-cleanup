<script setup lang="ts">
import { useThemeStore } from '../stores/themeStore'

const theme = useThemeStore()

const icons: Record<string, string> = {
  auto: 'pi pi-desktop',
  light: 'pi pi-sun',
  dark: 'pi pi-moon',
}
</script>

<template>
  <button
    @click="theme.cycle()"
    class="theme-toggle-btn cursor-pointer flex items-center gap-1.5 rounded px-2.5 py-1 text-sm
           text-indigo-200 hover:text-white hover:bg-indigo-500/30 dark:hover:bg-indigo-800/50 transition-colors"
    :title="`Theme: ${theme.mode}`"
  >
    <i :class="icons[theme.mode]" />
    <span class="capitalize">{{ theme.mode }}</span>
  </button>
</template>
