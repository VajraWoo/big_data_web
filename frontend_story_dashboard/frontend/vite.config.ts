import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

const proxy = { '/api': { target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000' } }

export default defineConfig({
  plugins: [vue()],
  server: { proxy, watch: { usePolling: true, interval: 500 } },
  preview: { proxy },
  test: { environment: 'jsdom', include: ['tests/unit/**/*.test.ts'] },
})
