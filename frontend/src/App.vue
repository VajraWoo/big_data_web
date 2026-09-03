<script setup lang="ts">
import { onMounted, ref, version as vueVersion } from 'vue'
import { version as echartsVersion } from 'echarts/core'

const state = ref<'checking' | 'ok' | 'database-error' | 'request-error'>('checking')

async function checkConnection() {
  state.value = 'checking'
  try {
    const response = await fetch('/api/v1/health', { signal: AbortSignal.timeout(8000) })
    if (response.status !== 200 && response.status !== 503) throw new Error('Unexpected response')
    const data = await response.json()
    if (response.ok && data.service === 'ok' && data.mongodb === 'ok') {
      state.value = 'ok'
    } else if (response.status === 503 && data.mongodb === 'unavailable') {
      state.value = 'database-error'
    } else {
      throw new Error('Invalid health response')
    }
  } catch {
    state.value = 'request-error'
  }
}

onMounted(checkConnection)
</script>

<template>
  <main>
    <p class="eyebrow">第一周 · 开发环境</p>
    <h1>Web 环境检查</h1>
    <p>此页面用于验证前端、后端和数据库连接，不是商家分析系统。</p>
    <section aria-live="polite" :class="state">
      <h2 v-if="state === 'checking'">正在检查连接…</h2>
      <h2 v-else-if="state === 'ok'">连接正常</h2>
      <h2 v-else-if="state === 'database-error'">数据库连接异常</h2>
      <h2 v-else>无法连接后端</h2>
      <p v-if="state === 'ok'">浏览器 → Vite 代理 → FastAPI → MongoDB 已连通。</p>
      <p v-else-if="state === 'database-error'">后端已响应，但 MongoDB 暂时不可用。</p>
      <p v-else-if="state === 'request-error'">请确认后端服务已启动，然后重新检查。</p>
      <button :disabled="state === 'checking'" @click="checkConnection">重新检查</button>
    </section>
    <dl>
      <div><dt>前端框架</dt><dd>Vue {{ vueVersion }}</dd></div>
      <div><dt>图表依赖</dt><dd>ECharts {{ echartsVersion }} 已加载</dd></div>
      <div><dt>业务数据</dt><dd>尚未生成分析结果</dd></div>
    </dl>
    <p class="note">真实评论清洗、NLP 和商家业务页面尚未实现。本页不展示模拟业务结论。</p>
  </main>
</template>

<style>
:root { font-family: system-ui, "Microsoft YaHei", sans-serif; color: #253344; background: #f5f7fa; }
body { margin: 0; }
main { max-width: 720px; margin: 70px auto; padding: 0 24px; }
.eyebrow { color: #576f85; font-size: 14px; }
h1 { font-size: 32px; margin: 12px 0; }
p { line-height: 1.8; }
section { margin: 30px 0; border: 1px solid #ccd5df; border-radius: 12px; padding: 24px; background: white; }
section.ok { border-left: 5px solid #27846c; }
section.database-error, section.request-error { border-left: 5px solid #bc493d; }
h2 { margin-top: 0; font-size: 22px; }
button { background: #204f76; color: white; border: 0; padding: 11px 18px; border-radius: 6px; cursor: pointer; font: inherit; }
button:disabled { opacity: .6; cursor: wait; }
button:focus-visible { outline: 3px solid #85b8de; outline-offset: 3px; }
dl div { display: flex; justify-content: space-between; gap: 20px; padding: 12px 0; border-bottom: 1px solid #dce3eb; }
dd { margin: 0; text-align: right; }
.note { color: #607184; font-size: 14px; margin-top: 25px; }
@media (max-width: 480px) { main { margin-top: 32px; } h1 { font-size: 28px; } }
</style>
