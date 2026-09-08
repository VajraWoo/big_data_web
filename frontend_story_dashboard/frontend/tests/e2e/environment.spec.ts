import { expect, test } from '@playwright/test'

test('business skeleton renders with explicit mock-data status', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '家电评论需求洞察与质量趋势分析' })).toBeVisible()
  await expect(page.getByText('开发数据', { exact: true })).toBeVisible()
  await expect(page.getByText('不是已验证 Gold')).toBeVisible()
  await expect(page.getByText('正式商品范围')).toBeVisible()
})
