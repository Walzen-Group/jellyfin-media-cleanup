import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// Inject git commit hash as a build-time constant (__GIT_HASH__).
// In Docker/CI, passed via VITE_GIT_HASH env var (since .git is excluded).
// Locally, just show "dev".
const gitHash = process.env.VITE_GIT_HASH || 'dev'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  define: {
    __GIT_HASH__: JSON.stringify(gitHash),
  },
  server: {
    host: '0.0.0.0',
    allowedHosts: true,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true }
    }
  }
})
