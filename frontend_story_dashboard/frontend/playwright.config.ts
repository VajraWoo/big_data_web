import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  workers: 1,
  use: { baseURL: process.env.WEB_BASE_URL || 'http://127.0.0.1:5173', headless: true },
  webServer: process.env.WEB_PREVIEW === '1' ? {
    command: 'npm run preview -- --host 127.0.0.1',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: false,
  } : undefined,
})
