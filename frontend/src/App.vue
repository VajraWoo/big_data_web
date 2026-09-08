<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { getJson } from './api/client'
import TrendChart from './components/TrendChart.vue'
import type { Facet, FacetName, Product, ReviewEvidence, Theme } from './types'

const products = ref<Product[]>([])
const selectedId = ref('')
const facets = ref<Facet[]>([])
const themes = ref<Theme[]>([])
const selectedTheme = ref<Theme | null>(null)
const reviews = ref<ReviewEvidence[]>([])
const activeFacet = ref<FacetName>('positive_evaluation')
const search = ref('')
const loading = ref(true)
const error = ref(false)

const selectedProduct = computed(() => products.value.find(item => item.parent_asin === selectedId.value))
const currentFacet = computed(() => facets.value.find(item => item.facet === activeFacet.value))

async function loadProducts() {
  loading.value = true; error.value = false
  try {
    const result = await getJson<{ data: { items: Product[] } }>(`/api/v1/products?q=${encodeURIComponent(search.value)}`)
    products.value = result.data.items
    if (!products.value.some(item => item.parent_asin === selectedId.value)) selectedId.value = products.value[0]?.parent_asin ?? ''
    if (selectedId.value) await loadOverview()
  } catch { error.value = true }
  finally { loading.value = false }
}

async function loadOverview() {
  const result = await getJson<{ data: { product: Product; facets: Facet[] } }>(`/api/v1/products/${selectedId.value}/overview`)
  facets.value = result.data.facets
  await loadThemes()
}

async function loadThemes() {
  selectedTheme.value = null; reviews.value = []
  const path = activeFacet.value === 'improvement'
    ? `/api/v1/products/${selectedId.value}/improvements`
    : `/api/v1/products/${selectedId.value}/themes?sentiment=${activeFacet.value === 'positive_evaluation' ? 'positive' : 'negative'}`
  const result = await getJson<{ data: { items: Theme[] } }>(path)
  themes.value = result.data.items
}

async function openTheme(theme: Theme) {
  const [detail, evidence] = await Promise.all([
    getJson<{ data: Theme }>(`/api/v1/themes/${theme.theme_id}`),
    getJson<{ data: { items: ReviewEvidence[] } }>(`/api/v1/themes/${theme.theme_id}/reviews?page=1&page_size=20`),
  ])
  selectedTheme.value = detail.data; reviews.value = evidence.data.items
}

watch(selectedId, async (value, old) => { if (value && old) await loadOverview() })
watch(activeFacet, async () => { if (selectedId.value) await loadThemes() })
onMounted(loadProducts)
</script>

<template>
  <div class="shell">
    <header>
      <div><p class="eyebrow">MERCHANT REVIEW INTELLIGENCE</p><h1>家电评论洞察</h1><p class="subtitle">从评价主题回到真实评论证据</p></div>
      <div class="target"><strong>139</strong><span>正式范围目标商品</span></div>
    </header>
    <aside class="dev-banner"><strong>开发数据</strong><span>当前展示的是 mock 样例，不是已验证 Gold，也不代表正式分析结论。</span><code>mock-development-v1</code></aside>

    <section v-if="error" class="state-card"><h2>暂时无法读取开发数据</h2><p>请确认 FastAPI 服务可用后重试。</p><button @click="loadProducts">重新加载</button></section>
    <section v-else-if="loading" class="state-card"><h2>正在加载商品与分析状态…</h2></section>
    <main v-else>
      <aside class="catalog">
        <div class="catalog-head"><h2>选择商品</h2><span>{{ products.length }} 个开发样例</span></div>
        <input v-model="search" type="search" placeholder="搜索商品或 ASIN" @keyup.enter="loadProducts">
        <button v-for="product in products" :key="product.parent_asin" class="product" :class="{ active: product.parent_asin === selectedId }" @click="selectedId = product.parent_asin">
          <span>{{ product.title }}</span><small>{{ product.category }} · {{ product.review_count }} 条评论</small>
        </button>
        <p v-if="!products.length" class="muted">没有匹配的开发样例。</p>
      </aside>

      <section v-if="selectedProduct" class="workspace">
        <div class="product-title"><div><span class="chip">{{ selectedProduct.category }}</span><h2>{{ selectedProduct.title }}</h2><p>{{ selectedProduct.parent_asin }} · {{ selectedProduct.review_count }} 条有效评论</p></div></div>
        <nav class="tabs" aria-label="分析维度">
          <button :class="{ active: activeFacet === 'positive_evaluation' }" @click="activeFacet = 'positive_evaluation'">正面评价</button>
          <button :class="{ active: activeFacet === 'negative_evaluation' }" @click="activeFacet = 'negative_evaluation'">负面评价</button>
          <button :class="{ active: activeFacet === 'improvement' }" @click="activeFacet = 'improvement'">产品改进需求</button>
        </nav>

        <div v-if="currentFacet?.status === 'processing'" class="state-card compact"><h3>分析处理中</h3><p>页面不会在请求期间启动模型或离线计算。</p></div>
        <div v-else-if="currentFacet?.status === 'failed'" class="state-card compact failed"><h3>该分析维度失败</h3><p>{{ currentFacet.error_summary }}</p></div>
        <div v-else-if="currentFacet?.empty_reason === 'no_qualified_theme'" class="state-card compact"><h3>无合格主题</h3><p>分析已完成，但没有满足正式准入条件的主题。</p></div>
        <div v-else class="content-grid">
          <div class="theme-list"><h3>主题 <span>{{ themes.length }}</span></h3>
            <button v-for="theme in themes" :key="theme.theme_id" class="theme" :class="{ active: selectedTheme?.theme_id === theme.theme_id }" @click="openTheme(theme)">
              <span><strong>{{ theme.name }}</strong><small>{{ theme.review_count }} 条唯一评论</small></span><b>→</b>
            </button>
            <p v-if="!themes.length" class="muted">暂无主题数据。</p>
          </div>
          <div class="detail">
            <template v-if="selectedTheme">
              <div class="metric"><div><small>主题</small><h3>{{ selectedTheme.name }}</h3></div><div><small>评论数</small><strong>{{ selectedTheme.review_count }}</strong></div><div><small>占比</small><strong>待定义</strong></div></div>
              <p class="ratio-note">占比分母与 mixed 规则等待新版下游口径确认。</p>
              <TrendChart :points="selectedTheme.trend ?? []" />
              <h3>评论原文</h3>
              <article v-for="review in reviews" :key="review.review_id"><div><span class="rating">★ {{ review.rating }}</span><time>{{ review.review_date }}</time></div><p>{{ review.text }}</p><blockquote v-if="review.evidence_text">{{ review.evidence_text }}</blockquote></article>
            </template>
            <div v-else class="select-hint"><span>↗</span><p>点击一个主题查看月度趋势和评论原文</p></div>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<style>
:root { font-family: Inter, "Microsoft YaHei", system-ui, sans-serif; color: #172033; background: #f3f5f8; font-synthesis: none; } * { box-sizing: border-box; } body { margin: 0; } button, input { font: inherit; } button { cursor: pointer; }
.shell { max-width: 1440px; margin: auto; padding: 32px; } header { display:flex; justify-content:space-between; align-items:end; margin-bottom:20px; } h1 { font-size:38px; margin:5px 0; letter-spacing:-1px; } h2,h3,p { margin-top:0; } .eyebrow { color:#2563eb; font-size:12px; font-weight:800; letter-spacing:1.8px; margin:0; } .subtitle,.muted { color:#667085; } .target { text-align:right; display:grid; } .target strong { font-size:34px; } .target span { color:#667085; font-size:13px; }
.dev-banner { display:flex; align-items:center; gap:14px; padding:13px 18px; background:#fff6dc; border:1px solid #efd891; border-radius:12px; margin-bottom:20px; color:#694d00; } .dev-banner span { flex:1; } .dev-banner code { background:#ffe8a3; padding:4px 8px; border-radius:5px; }
main { display:grid; grid-template-columns:290px 1fr; gap:20px; } .catalog,.workspace,.state-card { background:white; border:1px solid #e0e5ec; border-radius:16px; box-shadow:0 8px 30px rgba(20,31,50,.05); } .catalog { padding:18px; align-self:start; } .catalog-head { display:flex; justify-content:space-between; align-items:center; } .catalog-head h2 { font-size:18px; } .catalog-head span { color:#667085; font-size:12px; } input { width:100%; border:1px solid #d8dee8; border-radius:9px; padding:11px; margin-bottom:12px; }
.product { width:100%; text-align:left; border:0; background:transparent; border-radius:10px; padding:12px; display:grid; gap:5px; color:#172033; } .product small,.theme small { color:#667085; } .product.active { background:#edf4ff; color:#174ea6; }
.workspace { min-height:650px; padding:24px; } .product-title { display:flex; justify-content:space-between; } .product-title h2 { margin:10px 0 6px; } .product-title p { color:#667085; font-size:13px; } .chip { background:#eef2f7; padding:5px 8px; border-radius:6px; font-size:12px; }
.tabs { display:flex; gap:6px; border-bottom:1px solid #e3e7ed; margin:18px 0 22px; } .tabs button { border:0; background:transparent; padding:12px 18px; color:#667085; border-bottom:3px solid transparent; } .tabs button.active { color:#174ea6; border-color:#2563eb; font-weight:700; }
.content-grid { display:grid; grid-template-columns:300px 1fr; gap:22px; } .theme-list { border-right:1px solid #e7eaf0; padding-right:18px; } .theme-list h3 span { color:#667085; font-size:13px; } .theme { width:100%; display:flex; justify-content:space-between; align-items:center; text-align:left; padding:14px; border:1px solid #e1e6ed; border-radius:10px; background:white; margin-bottom:9px; } .theme span { display:grid; gap:5px; } .theme.active { border-color:#2563eb; background:#f4f8ff; }
.detail { min-width:0; } .metric { display:flex; gap:34px; align-items:center; } .metric div:first-child { flex:1; } .metric small { color:#667085; } .metric h3 { margin:4px 0; } .metric strong { font-size:20px; } .ratio-note { color:#866600; background:#fff9e8; padding:8px 10px; border-radius:7px; font-size:12px; } article { border-top:1px solid #e5e9ef; padding:15px 0; } article div { display:flex; justify-content:space-between; color:#667085; font-size:13px; } article p { margin:9px 0; line-height:1.6; } blockquote { margin:0; border-left:3px solid #7aa7e8; padding-left:10px; color:#4b6380; } .rating { color:#a66600; }
.state-card { padding:28px; } .state-card.compact { box-shadow:none; background:#f8fafc; } .state-card.failed { border-color:#efb2ad; background:#fff6f5; } .state-card button { border:0; border-radius:8px; background:#2563eb; color:white; padding:10px 15px; } .select-hint { min-height:420px; display:grid; place-content:center; text-align:center; color:#7b8798; } .select-hint span { font-size:35px; }
@media(max-width:900px){.shell{padding:18px}header{align-items:start}.target{display:none}.dev-banner{align-items:flex-start;flex-wrap:wrap}main{grid-template-columns:1fr}.catalog{max-height:250px;overflow:auto}.content-grid{grid-template-columns:1fr}.theme-list{border-right:0;border-bottom:1px solid #e7eaf0;padding:0 0 14px}.metric{flex-wrap:wrap}} @media(max-width:540px){h1{font-size:30px}.tabs{overflow:auto}.tabs button{white-space:nowrap;padding:10px}.workspace{padding:16px}.metric{gap:16px}}
</style>
