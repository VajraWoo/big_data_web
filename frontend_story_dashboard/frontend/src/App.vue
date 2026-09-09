<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { getJson } from './api/client'
import StoryTrendChart from './components/StoryTrendChart.vue'
import DynamicWordCloud from './components/DynamicWordCloud.vue'
import type { Facet, Product, ReviewEvidence, Theme } from './types'

type AnalysisMode = 'positive' | 'negative'

type ImprovementItem = {
  input_id: string
  taxonomy_id: string
  theme_id: string | null
  name: string
  improvement_suggestion: string
  support_insight_count: number
  support_review_count: number
  negative_insight_count: number
  mixed_insight_count: number
  generation_mode: string
  review_count: number
  ratio: {
    value: number | null
    status: string
    definition_id: string
  } | null
}

const products = ref<Product[]>([])
const selectedId = ref('')
const facets = ref<Facet[]>([])
const themes = ref<Theme[]>([])
const enrichedThemes = ref<Theme[]>([])
const selectedTheme = ref<Theme | null>(null)
const reviews = ref<ReviewEvidence[]>([])
const improvements = ref<ImprovementItem[]>([])
const activeMode = ref<AnalysisMode>('positive')
const category = ref('')
const loading = ref(true)
const detailLoading = ref(false)
const error = ref(false)
const detailError = ref(false)
const evidenceOpen = ref(false)
const showAllThemes = ref(false)

const selectedProduct = computed(() =>
  products.value.find(item => item.parent_asin === selectedId.value),
)

const currentFacet = computed(() => {
  const facetName =
    activeMode.value === 'positive'
      ? 'positive_evaluation'
      : 'negative_evaluation'

  return facets.value.find(item => item.facet === facetName)
})

const categories = computed(() =>
  Array.from(new Set(products.value.map(item => item.category))).sort(),
)

const activeMonths = computed(() => {
  const product = selectedProduct.value as Product & { active_month_count?: number }
  return product?.active_month_count ?? '—'
})

const facetLabel = computed(() =>
  activeMode.value === 'positive' ? '正面评价' : '负面评价',
)

const currentItemCount = computed(() => themes.value.length)

const visibleThemes = computed(() =>
  showAllThemes.value ? themes.value : themes.value.slice(0, 8),
)

const selectedImprovement = computed(() => {
  if (!selectedTheme.value || selectedTheme.value.sentiment !== 'negative') {
    return null
  }

  const selectedTaxonomyId = (
    selectedTheme.value as Theme & { taxonomy_id?: string }
  ).taxonomy_id

  return (
    improvements.value.find(item =>
      item.theme_id === selectedTheme.value?.theme_id ||
      (
        selectedTaxonomyId &&
        item.taxonomy_id === selectedTaxonomyId
      ),
    ) ?? null
  )
})

function shortProductTitle(title: string) {
  const firstClause = title.split(',')[0]?.trim() || title.trim()
  const maxLength = 58

  return firstClause.length > maxLength
    ? `${firstClause.slice(0, maxLength).trimEnd()}…`
    : firstClause
}

async function loadProducts() {
  loading.value = true
  error.value = false

  try {
    const params = new URLSearchParams()

    if (category.value) {
      params.set('category', category.value)
    }

    const result = await getJson<{ data: { items: Product[] } }>(
      `/api/v1/products?${params}`,
    )

    products.value = result.data.items

    if (!products.value.some(item => item.parent_asin === selectedId.value)) {
      selectedId.value = products.value[0]?.parent_asin ?? ''
    }

    if (selectedId.value) {
      await loadOverview()
    }
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

async function loadOverview() {
  detailLoading.value = true
  detailError.value = false

  try {
    const result = await getJson<{
      data: {
        product: Product
        facets: Facet[]
      }
    }>(`/api/v1/products/${selectedId.value}/overview`)

    facets.value = result.data.facets

    await loadAnalysis()
  } catch {
    detailError.value = true
  } finally {
    detailLoading.value = false
  }
}

async function loadAnalysis() {
  selectedTheme.value = null
  reviews.value = []
  enrichedThemes.value = []
  themes.value = []
  improvements.value = []
  evidenceOpen.value = false
  detailError.value = false
  showAllThemes.value = false

  try {
    const sentiment =
      activeMode.value === 'positive'
        ? 'positive'
        : 'negative'

    const path =
      `/api/v1/products/${selectedId.value}/themes?sentiment=${sentiment}`

    const result = await getJson<{
      data: {
        items: Theme[]
      }
    }>(path)

    themes.value = result.data.items

    if (sentiment === 'negative') {
      const improvementResult = await getJson<{
        data: {
          items: ImprovementItem[]
        }
      }>(`/api/v1/products/${selectedId.value}/improvements`)

      improvements.value = improvementResult.data.items
    }

    const details = await Promise.all(
      themes.value.slice(0, 8).map(async theme => {
        try {
          return (
            await getJson<{ data: Theme }>(
              `/api/v1/themes/${theme.theme_id}`,
            )
          ).data
        } catch {
          return theme
        }
      }),
    )

    enrichedThemes.value = details
  } catch {
    detailError.value = true
    themes.value = []
    improvements.value = []
    enrichedThemes.value = []
  }
}

async function openTheme(theme: Theme) {
  detailLoading.value = true
  detailError.value = false

  try {
    const [detail, evidence] = await Promise.all([
      getJson<{ data: Theme }>(
        `/api/v1/themes/${theme.theme_id}`,
      ),
      getJson<{
        data: {
          items: ReviewEvidence[]
        }
      }>(
        `/api/v1/themes/${theme.theme_id}/reviews?page=1&page_size=20`,
      ),
    ])

    selectedTheme.value = detail.data
    reviews.value = evidence.data.items
    evidenceOpen.value = true
  } catch {
    detailError.value = true
  } finally {
    detailLoading.value = false
  }
}

watch(selectedId, async (value, oldValue) => {
  if (value && oldValue) {
    await loadOverview()
  }
})

watch(activeMode, async () => {
  if (selectedId.value) {
    await loadAnalysis()
  }
})

onMounted(loadProducts)
</script>

<template>
  <div class="dashboard-shell">
    <div class="ambient ambient-a"></div>
    <div class="ambient ambient-b"></div>

    <header class="hero">
      <div>
        <h1>家电评论需求洞察与质量趋势分析</h1>
        <p class="subtitle">
          把海量评论压缩成趋势、主题与可追溯证据，让产品问题一眼可见。
        </p>
      </div>
    </header>

    <section class="control-bar">
      <div class="select-block product-select">
        <label>当前商品</label>

        <select
          v-model="selectedId"
          aria-label="当前商品"
        >
          <option
            v-for="product in products"
            :key="product.parent_asin"
            :value="product.parent_asin"
            :title="product.title"
          >
            {{ shortProductTitle(product.title) }}
          </option>
        </select>
      </div>

      <div class="select-block category-select">
        <label>类别</label>

        <select
          v-model="category"
          aria-label="商品类别"
          @change="loadProducts"
        >
          <option value="">
            全部类别
          </option>

          <option
            v-for="item in categories"
            :key="item"
            :value="item"
          >
            {{ item }}
          </option>
        </select>
      </div>

      <nav
        class="segmented"
        aria-label="分析维度"
      >
        <button
          :class="{ active: activeMode === 'positive' }"
          @click="activeMode = 'positive'"
        >
          正面
        </button>

        <button
          :class="{ active: activeMode === 'negative' }"
          @click="activeMode = 'negative'"
        >
          负面
        </button>

      </nav>
    </section>

    <section
      v-if="error"
      class="state-card"
    >
      <h2>暂时无法读取数据</h2>
      <p>请确认 FastAPI 服务可用后重试。</p>
      <button @click="loadProducts">
        重新加载
      </button>
    </section>

    <section
      v-else-if="loading"
      class="state-card"
    >
      <h2>正在加载可视化页面…</h2>
    </section>

    <main
      v-else-if="selectedProduct"
      class="dashboard"
    >
      <section class="kpi-row">
        <article>
          <span>有效评论</span>
          <strong>
            {{ selectedProduct.review_count.toLocaleString() }}
          </strong>
        </article>

        <article>
          <span>当前主题</span>
          <strong>{{ currentItemCount }}</strong>
        </article>

        <article>
          <span>活跃月份</span>
          <strong>{{ activeMonths }}</strong>
        </article>
      </section>

      <section
        v-if="detailError"
        class="state-card compact failed"
      >
        <h3>分析数据读取失败</h3>
        <button @click="loadOverview">
          重试详情
        </button>
      </section>

      <section
        v-else-if="currentFacet?.status === 'processing'"
        class="state-card compact"
      >
        <h3>该维度正在处理中</h3>
      </section>

      <section
        v-else-if="currentFacet?.status === 'failed'"
        class="state-card compact failed"
      >
        <h3>该分析维度失败</h3>
        <p>{{ currentFacet.error_summary }}</p>
      </section>

      <section
        v-else-if="
          currentFacet?.empty_reason === 'no_qualified_theme'
        "
        class="state-card compact"
      >
        <h3>无合格主题</h3>
        <p>
          分析已完成，但没有满足当前准入条件的主题。
        </p>
      </section>

      <template v-else>
        <section class="panel ranking-panel">
          <div class="panel-head">
            <div>
              <h2>{{ facetLabel }}主题排行</h2>
              <span>
                点击主题可查看趋势、改进建议与原始评论证据
              </span>
            </div>

            <div class="theme-count-actions">
              <strong>
                {{ themes.length }} 个主题
              </strong>

              <button
                v-if="themes.length > 8"
                class="show-all-button"
                @click="showAllThemes = !showAllThemes"
              >
                {{
                  showAllThemes
                    ? '收起'
                    : `查看全部 ${themes.length} 个`
                }}
              </button>
            </div>
          </div>

          <div class="ranking-list">
            <button
              v-for="(theme, index) in visibleThemes"
              :key="theme.theme_id"
              class="rank-row"
              @click="openTheme(theme)"
            >
              <i>
                {{ String(index + 1).padStart(2, '0') }}
              </i>

              <span>
                <b>{{ theme.name }}</b>
                <small>
                  {{ theme.review_count }} 条唯一评论
                </small>
              </span>

              <div class="bar">
                <em
                  :style="{
                    width: `${Math.max(
                      12,
                      (theme.review_count /
                        (themes[0]?.review_count || 1)) *
                        100,
                    )}%`,
                  }"
                ></em>
              </div>

              <strong>
                {{ theme.review_count }}
              </strong>
            </button>
          </div>

          <p
            v-if="!themes.length"
            class="muted"
          >
            暂无主题数据。
          </p>
        </section>

        <section class="visual-grid">
          <article class="panel trend-panel">
            <div class="panel-head">
              <div>
                <h2>核心主题走势</h2>
                <span>
                  观察主要主题随月份的变化
                </span>
              </div>
            </div>

            <StoryTrendChart
              :themes="enrichedThemes"
            />
          </article>

          <article class="panel cloud-panel">
            <div class="panel-head">
              <div>
                <h2>动态主题词云</h2>
                <span>
                  点击词语可直接下钻评论证据
                </span>
              </div>
            </div>

            <DynamicWordCloud
              :themes="themes"
              @select="openTheme"
            />
          </article>
        </section>
      </template>
    </main>

    <aside
      v-if="evidenceOpen && selectedTheme"
      class="drawer-backdrop"
      @click.self="evidenceOpen = false"
    >
      <section class="drawer">
        <button
          class="drawer-close"
          @click="evidenceOpen = false"
        >
          ×
        </button>

        <h2>{{ selectedTheme.name }}</h2>

        <div class="drawer-metrics">
          <div>
            <span>评论数</span>
            <strong>
              {{ selectedTheme.review_count }}
            </strong>
          </div>

          <div>
            <span>占比</span>

            <strong>
              {{
                selectedTheme.ratio?.status === 'ready' &&
                selectedTheme.ratio?.value != null
                  ? `${(
                      selectedTheme.ratio.value * 100
                    ).toFixed(1)}%`
                  : '—'
              }}
            </strong>
          </div>
        </div>

        <StoryTrendChart
          :themes="[selectedTheme]"
        />

        <section
          v-if="selectedImprovement"
          class="drawer-improvement"
        >
          <span>产品改进建议</span>
          <p>
            {{ selectedImprovement.improvement_suggestion }}
          </p>
          <small>
            {{ selectedImprovement.support_review_count }} 条评论支撑
          </small>
        </section>

        <h3>真实评论证据</h3>

        <article
          v-for="review in reviews"
          :key="review.review_id"
          class="review"
        >
          <div>
            <span class="review-rating">★ {{ review.rating }}</span>
            <time>{{ review.review_date }}</time>
          </div>

          <p>{{ review.text }}</p>

          <blockquote
            v-if="review.evidence_text"
          >
            {{ review.evidence_text }}
          </blockquote>
        </article>
      </section>
    </aside>
  </div>
</template>

<style>
:root {
  font-family:
    Inter,
    "Microsoft YaHei",
    system-ui,
    sans-serif;

  color: #152033;
  background: #eef2f7;
  font-synthesis: none;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;

  background:
    linear-gradient(
      180deg,
      #f9fbfd 0,
      #eef2f7 100%
    );
}

button,
select {
  font: inherit;
}

.dashboard-shell {
  position: relative;

  max-width: 1600px;
  margin: auto;
  padding: 34px 40px 56px;

  overflow: hidden;
}

.ambient {
  position: absolute;

  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.16;

  pointer-events: none;
}

.ambient-a {
  width: 400px;
  height: 400px;

  right: -180px;
  top: -120px;

  background: #60a5fa;
}

.ambient-b {
  width: 320px;
  height: 320px;

  left: -180px;
  top: 420px;

  background: #a78bfa;
}

.hero {
  position: relative;
  margin-bottom: 24px;
}

.hero h1 {
  margin: 0 0 10px;

  font-size: 42px;
  line-height: 1.08;
  letter-spacing: -0.045em;
}

.subtitle {
  margin: 0;

  color: #5f6e82;
  font-size: 16px;
  line-height: 1.6;
}

.control-bar {
  position: relative;

  display: grid;

  grid-template-columns:
    minmax(0, 2fr)
    minmax(180px, 0.8fr)
    auto;

  align-items: end;

  gap: 16px;

  padding: 16px 18px;
  margin-bottom: 18px;

  background:
    rgba(255, 255, 255, 0.9);

  border:
    1px solid #dde4ee;

  border-radius: 18px;

  box-shadow:
    0 14px 40px
    rgba(31, 41, 55, 0.07);

  backdrop-filter: blur(14px);
}

.select-block {
  display: grid;
  gap: 7px;

  min-width: 0;
}

.select-block label {
  color: #66758a;

  font-size: 13px;
  font-weight: 700;
}

.select-block select {
  width: 100%;
  min-width: 0;
  height: 42px;

  padding:
    0 34px
    0 12px;

  color: #1f2a3d;

  font-size: 14px;

  background: #fff;

  border:
    1px solid #d8e0ea;

  border-radius: 10px;
}

.segmented {
  display: flex;

  align-self: end;

  flex: 0 0 auto;

  padding: 4px;

  background: #f0f4f9;

  border-radius: 11px;
}

.segmented button {
  min-width: 88px;

  padding: 9px 16px;

  color: #647286;
  font-size: 14px;

  background: transparent;

  border: 0;
  border-radius: 8px;

  cursor: pointer;
}

.segmented button.active {
  color: white;
  font-weight: 700;

  background: #172033;

  box-shadow:
    0 5px 15px
    rgba(23, 32, 51, 0.16);
}

.dashboard {
  position: relative;
}

.kpi-row {
  display: grid;

  grid-template-columns:
    repeat(3, 1fr);

  gap: 14px;

  margin-bottom: 14px;
}

.theme-count-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.show-all-button {
  padding: 7px 11px;
  color: #1d4ed8;
  font-size: 14px;
  font-weight: 700;
  background: #eff6ff;
  border: 0;
  border-radius: 9px;
  cursor: pointer;
}

.show-all-button:hover {
  background: #dbeafe;
}

.drawer-improvement {
  margin: 22px 0 26px;
  padding: 18px 20px;
  background: #f7f9fc;
  border-left: 4px solid #4f7df3;
  border-radius: 10px;
}

.drawer-improvement > span {
  display: block;
  margin-bottom: 8px;
  color: #50627c;
  font-size: 15px;
  font-weight: 700;
}

.drawer-improvement p {
  margin: 0;
  color: #1f2d42;
  font-size: 16px;
  line-height: 1.8;
}

.drawer-improvement small {
  display: block;
  margin-top: 9px;
  color: #7a8798;
  font-size: 14px;
}

.state-card {
  background:
    rgba(255, 255, 255, 0.94);

  border:
    1px solid #dde5ef;

  border-radius: 18px;

  box-shadow:
    0 16px 35px
    rgba(31, 41, 55, 0.055);
}

.kpi-row article {
  display: grid;
  gap: 7px;

  padding: 20px 22px;
}

.kpi-row span {
  color: #68788d;

  font-size: 14px;
  font-weight: 600;
}

.kpi-row strong {
  font-size: 30px;

  letter-spacing:
    -0.04em;
}

.panel {
  min-width: 0;

  padding: 20px;
}

.ranking-panel {
  margin-bottom: 14px;
}

.panel-head {
  display: flex;

  justify-content:
    space-between;

  align-items:
    flex-start;

  gap: 18px;

  margin-bottom: 12px;
}

.panel-head h2 {
  margin: 0 0 5px;

  font-size: 21px;

  letter-spacing:
    -0.02em;
}

.panel-head span,
.panel-head > strong {
  color: #7a8798;

  font-size: 13px;
  font-weight: 500;
}

.panel-head > strong {
  margin-top: 4px;

  white-space: nowrap;
}

.ranking-list {
  display: grid;

  grid-template-columns:
    1fr 1fr;

  column-gap: 28px;
}

.rank-row {
  width: 100%;

  display: grid;

  grid-template-columns:
    34px
    minmax(150px, 1.2fr)
    1fr
    52px;

  align-items: center;

  gap: 12px;

  padding: 13px 2px;

  text-align: left;

  background: transparent;

  border: 0;
  border-top:
    1px solid #edf1f5;

  cursor: pointer;
}

.rank-row:nth-child(-n + 2) {
  border-top: 0;
}

.rank-row i {
  color: #93a0b2;

  font-size: 12px;
  font-style: normal;
  font-weight: 800;
}

.rank-row span {
  display: grid;
  gap: 3px;

  min-width: 0;
}

.rank-row b {
  font-size: 14px;

  overflow-wrap: anywhere;
}

.rank-row small {
  color: #7b889a;

  font-size: 12px;
}

.rank-row strong {
  text-align: right;

  font-size: 13px;
}

.bar {
  height: 7px;

  overflow: hidden;

  background: #eef2f7;

  border-radius: 999px;
}

.bar em {
  display: block;

  height: 100%;

  background:
    linear-gradient(
      90deg,
      #60a5fa,
      #2563eb
    );

  border-radius: inherit;
}

.visual-grid {
  display: grid;

  grid-template-columns:
    1.15fr 0.85fr;

  gap: 14px;
}

.state-card {
  padding: 28px;
}

.state-card.compact {
  margin-bottom: 14px;

  box-shadow: none;
}

.state-card.failed {
  background: #fff7f6;

  border-color: #f0b6b0;
}

.state-card button {
  padding: 9px 14px;

  color: white;

  background: #172033;

  border: 0;
  border-radius: 9px;

  cursor: pointer;
}

.muted {
  color: #94a3b8;

  font-size: 14px;
}

.drawer-backdrop {
  position: fixed;
  inset: 0;

  z-index: 30;

  display: flex;
  justify-content: flex-end;

  background:
    rgba(15, 23, 42, 0.2);

  backdrop-filter: blur(5px);
}

.drawer {
  position: relative;

  width:
    min(650px, 94vw);

  height: 100%;

  overflow: auto;

  padding: 30px 32px;

  background: #fff;

  box-shadow:
    -28px 0 70px
    rgba(15, 23, 42, 0.16);
}

.drawer-close {
  position: absolute;

  right: 22px;
  top: 18px;

  width: 38px;
  height: 38px;

  color: #5d6a7c;

  font-size: 24px;

  background: #eef2f7;

  border: 0;
  border-radius: 50%;

  cursor: pointer;
}

.drawer h2 {
  margin:
    0 52px
    20px 0;

  font-size: 29px;
}

.drawer h3 {
  margin-top: 22px;

  font-size: 19px;
}

.drawer-metrics {
  display: flex;

  gap: 12px;

  margin-bottom: 10px;
}

.drawer-metrics div {
  min-width: 130px;

  display: grid;
  gap: 4px;

  padding: 13px 17px;

  background: #f5f7fa;

  border-radius: 12px;
}

.drawer-metrics span {
  color: #718096;

  font-size: 13px;
}

.drawer-metrics strong {
  font-size: 21px;
}

.review {
  padding: 16px 0;

  border-top:
    1px solid #e9edf2;
}

.review > div {
  display: flex;

  justify-content:
    space-between;

  gap: 16px;

  color: #7d8999;

  font-size: 15px;
}

.review-rating {
  color: #b7791f;
  font-size: 18px;
  font-weight: 800;
}

.review time {
  font-size: 14px;
}

.review p {
  margin: 12px 0;
  font-size: 16px;
  line-height: 1.8;
}

.review blockquote {
  margin: 0;

  padding: 10px 13px;

  color: #42556f;

  font-size: 15px;
  line-height: 1.75;

  background: #f6f9fc;

  border-left:
    3px solid #60a5fa;

  border-radius:
    0 8px 8px 0;
}

@media (max-width: 1100px) {
  .dashboard-shell {
    padding: 22px;
  }

  .hero h1 {
    font-size: 34px;
  }

  .control-bar {
    grid-template-columns:
      1fr 1fr;
  }

  .product-select {
    grid-column:
      1 / -1;
  }

  .segmented {
    justify-self: end;
  }

  .kpi-row {
    grid-template-columns:
      repeat(2, 1fr);
  }

  .ranking-list,
  .visual-grid,
  .improvement-list {
    grid-template-columns:
      1fr;
  }

  .rank-row:nth-child(2) {
    border-top:
      1px solid #edf1f5;
  }
}

@media (max-width: 650px) {
  .dashboard-shell {
    padding: 16px;
  }

  .hero h1 {
    font-size: 30px;
  }

  .subtitle {
    font-size: 15px;
  }

  .control-bar {
    grid-template-columns:
      1fr;
  }

  .product-select {
    grid-column: auto;
  }

  .segmented {
    width: 100%;

    justify-self: stretch;
  }

  .segmented button {
    flex: 1;
  }

  .kpi-row {
    grid-template-columns:
      1fr 1fr;
  }

  .kpi-row article {
    padding: 16px;
  }

  .rank-row {
    grid-template-columns:
      28px
      1fr
      42px;
  }

  .rank-row .bar {
    display: none;
  }

  .panel {
    padding: 16px;
  }
}

/* ===== Final layout / typography correction ===== */

.kpi-row {
  gap: 20px;
  margin: 18px 0 24px;
}

.kpi-row article {
  display: grid;
  gap: 8px;
  padding: 22px 26px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid #dde6f0;
  border-radius: 18px;
  box-shadow: 0 10px 28px rgba(29, 43, 67, 0.06);
}

.kpi-row span {
  color: #66778d;
  font-size: 17px;
  font-weight: 700;
}

.kpi-row strong {
  color: #142033;
  font-size: 40px;
  line-height: 1.05;
  letter-spacing: -0.035em;
}

.panel {
  display: block;
  min-width: 0;
  padding: 24px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid #dde6f0;
  border-radius: 18px;
  box-shadow: 0 10px 28px rgba(29, 43, 67, 0.05);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 16px;
}

.panel-head h2 {
  margin: 0 0 7px;
  color: #142033;
  font-size: 25px;
  line-height: 1.3;
}

.panel-head span {
  color: #697b91;
  font-size: 16px;
  line-height: 1.6;
  font-weight: 500;
}

.theme-count-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 0 0 auto;
  white-space: nowrap;
}

.theme-count-actions > strong {
  color: #26364d;
  font-size: 18px;
  font-weight: 800;
}

.show-all-button {
  min-width: 86px;
  padding: 9px 17px;
  color: #2458c6;
  font-size: 15px;
  line-height: 1;
  font-weight: 800;
  background: #eef4ff;
  border: 1px solid #d7e4ff;
  border-radius: 999px;
  box-shadow: none;
  cursor: pointer;
}

.show-all-button:hover {
  background: #e3edff;
  border-color: #c5d8ff;
}

.ranking-list {
  column-gap: 34px;
}

.rank-row {
  padding: 15px 2px;
}

.rank-row i {
  color: #8798ad;
  font-size: 14px;
}

.rank-row b {
  color: #152033;
  font-size: 17px;
  line-height: 1.4;
}

.rank-row small {
  color: #74869c;
  font-size: 15px;
  line-height: 1.45;
}

.rank-row strong {
  font-size: 16px;
}

.visual-grid {
  gap: 18px;
}

.trend-panel,
.cloud-panel {
  min-width: 0;
}

.muted {
  color: #708196;
  font-size: 16px;
  line-height: 1.65;
}

/* Drawer / evidence: make all supporting text comfortably readable. */
.drawer h2 {
  font-size: 36px;
}

.drawer h3 {
  font-size: 25px;
}

.drawer-metrics span {
  color: #687a90;
  font-size: 17px;
}

.drawer-metrics strong {
  font-size: 30px;
}

.drawer-improvement > span {
  font-size: 17px;
}

.drawer-improvement p {
  font-size: 17px;
  line-height: 1.8;
}

.drawer-improvement small {
  color: #6f8196;
  font-size: 15px;
}

.review > div span,
.review time {
  font-size: 15px;
}

.review-rating {
  font-size: 21px !important;
}

.review p {
  font-size: 17px;
  line-height: 1.85;
}

.review blockquote {
  color: #38516e;
  font-size: 16px;
  line-height: 1.8;
}

/* Other gray/helper text on the page. */
.hero p,
.controls label,
.controls small,
.control-label,
.selector label,
.selector small {
  color: #697b91 !important;
  font-size: 16px !important;
  line-height: 1.55;
}

@media (max-width: 900px) {
  .kpi-row strong {
    font-size: 34px;
  }

  .panel-head h2 {
    font-size: 23px;
  }

  .theme-count-actions {
    white-space: normal;
  }
}

</style>