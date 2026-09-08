import { expect, test } from '@playwright/test'

test('API outage is visible and retryable', async ({ page }) => {
  await page.route('**/api/v1/products**', route => route.abort('failed'))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '暂时无法读取开发数据' })).toBeVisible()
  await expect(page.getByRole('button', { name: '重新加载' })).toBeVisible()
})
