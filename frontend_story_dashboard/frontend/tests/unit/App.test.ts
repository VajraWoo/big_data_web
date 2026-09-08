import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../../src/App.vue'

const overview = {
  data: {
    product: { parent_asin: 'MOCK-ICE-001', title: '开发示例：台式制冰机', category: 'Ice Makers', review_count: 842 },
    facets: [
      { facet: 'positive_evaluation', status: 'ready', theme_count: 1, empty_reason: null, error_summary: null },
      { facet: 'negative_evaluation', status: 'ready', theme_count: 0, empty_reason: 'no_qualified_theme', error_summary: null },
      { facet: 'improvement', status: 'processing', theme_count: null, empty_reason: null, error_summary: null },
    ],
  },
  meta: { data_source: 'mock', is_gold: false, batch_id: 'mock-development-v1' },
}

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body }
}

afterEach(() => vi.unstubAllGlobals())

it('shows the insight workflow and an unmistakable development-data notice', async () => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/overview')) return ok(overview)
    if (url.includes('/themes?sentiment=positive')) return ok({ data: { facet: overview.data.facets[0], items: [] }, meta: overview.meta })
    return ok({ data: { items: [overview.data.product] }, pagination: { page: 1, page_size: 20, total_items: 1, total_pages: 1 }, meta: overview.meta })
  }))
  const page = mount(App)
  await flushPromises()
  expect(page.text()).toContain('家电评论需求洞察与质量趋势分析')
  expect(page.text()).toContain('开发数据')
  expect(page.text()).toContain('不是已验证 Gold')
  expect(page.text()).toContain('开发示例：台式制冰机')
  expect(page.text()).toContain('正面评价')
  expect(page.text()).toContain('负面评价')
  expect(page.text()).toContain('产品改进需求')
  expect(page.text()).toContain('正式商品范围')
  expect(page.get('select[aria-label="商品类别"]').exists()).toBe(true)
})

it('shows an actionable request failure instead of business results', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
  const page = mount(App)
  await flushPromises()
  expect(page.text()).toContain('暂时无法读取开发数据')
  expect(page.get('button').text()).toContain('重新加载')
})
