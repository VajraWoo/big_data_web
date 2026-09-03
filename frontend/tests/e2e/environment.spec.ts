import { expect, test } from '@playwright/test'

test('real backend and MongoDB connectivity, desktop and mobile layout', async ({ page }) => {
  const pageErrors: string[] = []
  page.on('pageerror', error => pageErrors.push(error.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Web 环境检查' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '连接正常', exact: true })).toBeVisible()
  await expect(page.getByText('尚未生成分析结果')).toBeVisible()
  const response = await page.request.get('/api/v1/health')
  expect(response.status()).toBe(200)
  expect(await response.json()).toEqual({ service: 'ok', mongodb: 'ok', active_run: null })
  await page.screenshot({ path: '../tmp/web-environment-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('button', { name: '重新检查' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: '../tmp/web-environment-mobile.png', fullPage: true })
  expect(pageErrors).toEqual([])
})

test('network failure is visible and retry recovers', async ({ page }) => {
  await page.route('**/api/v1/health', route => route.abort('failed'))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '无法连接后端' })).toBeVisible()
  await page.unroute('**/api/v1/health')
  await page.getByRole('button', { name: '重新检查' }).click()
  await expect(page.getByRole('heading', { name: '连接正常', exact: true })).toBeVisible()
})
