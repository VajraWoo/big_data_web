import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../../src/App.vue'

afterEach(() => vi.unstubAllGlobals())

it('shows actual connectivity and clearly labels the environment-only scope', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true, status: 200,
    json: async () => ({ service: 'ok', mongodb: 'ok', active_run: null }),
  }))
  const page = mount(App)
  await flushPromises()
  expect(page.text()).toContain('Web 环境检查')
  expect(page.text()).toContain('连接正常')
  expect(page.text()).toContain('尚未生成分析结果')
  page.unmount()
})

it('shows database failure instead of a false success', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: false, status: 503,
    json: async () => ({ service: 'degraded', mongodb: 'unavailable', active_run: null }),
  }))
  const page = mount(App)
  await flushPromises()
  expect(page.text()).toContain('数据库连接异常')
  expect(page.text()).not.toContain('连接正常')
  page.unmount()
})

it('shows a request error and allows retrying', async () => {
  const request = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({
    ok: true, status: 200,
    json: async () => ({ service: 'ok', mongodb: 'ok', active_run: null }),
  })
  vi.stubGlobal('fetch', request)
  const page = mount(App)
  await flushPromises()
  expect(page.text()).toContain('无法连接后端')
  await page.get('button').trigger('click')
  await flushPromises()
  expect(page.text()).toContain('连接正常')
  page.unmount()
})
