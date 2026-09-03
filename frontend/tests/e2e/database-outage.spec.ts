import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { expect, test } from '@playwright/test'

test('real MongoDB outage returns 503 and recovery restores the page', async ({ page }) => {
  test.setTimeout(120_000)
  const cwd = resolve(import.meta.dirname, '../../..')
  const compose = ['compose', '-f', 'infra/compose.yaml', '-f', 'infra/compose.web.yaml', '--profile', 'web']
  try {
    execFileSync('docker', [...compose, 'stop', 'mongodb'], { cwd, timeout: 30_000 })
    await page.goto('/')
    await expect(page.getByRole('heading', { name: '数据库连接异常' })).toBeVisible({ timeout: 15_000 })
    const response = await page.request.get('/api/v1/health')
    expect(response.status()).toBe(503)
    expect(await response.json()).toEqual({ service: 'degraded', mongodb: 'unavailable', active_run: null })
  } finally {
    execFileSync('docker', [...compose, 'up', '-d', '--wait', '--wait-timeout', '60', 'mongodb'], { cwd, timeout: 90_000 })
  }
  await page.getByRole('button', { name: '重新检查' }).click()
  await expect(page.getByRole('heading', { name: '连接正常', exact: true })).toBeVisible({ timeout: 15_000 })
})
